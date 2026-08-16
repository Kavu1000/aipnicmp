package la.aipnicmp.collector.collect

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.location.Location
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import la.aipnicmp.collector.CollectorPrefs
import la.aipnicmp.collector.R
import la.aipnicmp.collector.data.MeasurementStore
import la.aipnicmp.collector.data.NetworkStatus
import la.aipnicmp.collector.ui.MainActivity
import la.aipnicmp.collector.upload.UploadScheduler

/**
 * Collection runs here, in a foreground service, and it has to.
 *
 * From Android 10, `getAllCellInfo()` is throttled for background apps and
 * returns cached results rather than a fresh scan. A plain background service
 * would therefore quietly report stale readings — the worst possible failure
 * for this project, because the data would look fine and be wrong. A foreground
 * service with a visible notification is the only way to sample honestly while
 * the phone is in someone's pocket on a bus.
 *
 * The notification is not a nuisance to be minimised, either: someone carrying
 * this app deserves to see, at a glance, that it is recording.
 */
class CollectionService : Service() {

    companion object {
        private const val TAG = "CollectionService"
        private const val CHANNEL_ID = "collection"
        private const val NOTIFICATION_ID = 1

        const val ACTION_START = "la.aipnicmp.collector.START"
        const val ACTION_STOP = "la.aipnicmp.collector.STOP"

        /** Broadcast so the UI can show progress without binding to the service. */
        const val ACTION_STATE_CHANGED = "la.aipnicmp.collector.STATE_CHANGED"

        /**
         * Shortest gap between throughput tests.
         *
         * Wall-clock rather than a count of samples. A sample count meant the
         * rate depended on how fast the collector was moving — a phone standing
         * still gates to one sample a minute and tested rarely, while the same
         * phone in a car tested several times as often over the same period.
         * Time is what the data budget is actually spent against, so time is
         * what schedules it.
         *
         * At five minutes this is twelve runs an hour, and each run is
         * PAYLOAD_BYTES. Against the 20 MB daily budget that is about eighty
         * runs, so a phone collecting continuously reaches the ceiling in
         * something under seven hours and then stops testing until midnight.
         * That is the budget doing its job rather than a fault, but it is the
         * reason to change one if the other changes.
         */
        /**
         * Records that may be waiting and still allow a throughput test.
         *
         * Above this the phone is draining a backlog, and those records matter
         * more than a speed sample. Below it, this is just the last reading or
         * two still in flight.
         */
        private const val MAX_QUEUE_FOR_SPEED_TEST = 5

        private const val SPEED_TEST_INTERVAL_MILLIS = 5 * 60 * 1000L

        /** Above this, the fix came from wifi or cell towers rather than GPS. */
        private const val MAX_ACCURACY_METRES = 50f

        /** Older than this and the phone may have moved since the fix was taken. */
        private const val MAX_FIX_AGE_MILLIS = 90_000L

        /**
         * Ceiling on how long one sample may hold the processor awake. Long
         * enough for a throughput test on a bad link, short enough that a stuck
         * sample cannot flatten a collector's battery unnoticed.
         */
        private const val WAKE_LOCK_TIMEOUT_MILLIS = 60_000L

        @Volatile
        var isRunning: Boolean = false
            private set

        fun start(context: Context) {
            val intent = Intent(context, CollectionService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.startService(Intent(context, CollectionService::class.java).setAction(ACTION_STOP))
        }
    }

    private lateinit var store: MeasurementStore
    private lateinit var prefs: CollectorPrefs
    private lateinit var radio: RadioSampler
    private lateinit var location: FusedLocationProviderClient
    private val sampler = Sampler()

    private var recordedThisSession = 0

    /**
     * One background thread for the sampling path.
     *
     * The location callback arrives on the main looper, and a throughput test
     * is a network read of a quarter of a megabyte — on the main thread that is
     * an immediate NetworkOnMainThreadException, and on a slow link it would
     * freeze the UI for twenty seconds. A single thread rather than a pool so
     * samples stay in order and two tests can never run at once.
     */
    private val work = java.util.concurrent.Executors.newSingleThreadExecutor()

    /**
     * When the last throughput test ran, as elapsed time since boot.
     *
     * Not wall-clock: the system clock can jump when the network corrects it,
     * and a jump backwards would suspend testing for as long as the correction,
     * while a jump forwards would fire one immediately. Zero means "not yet
     * this session", so the first sample after starting always tests.
     */
    private var lastSpeedTestAtMillis = 0L

    /**
     * Keeps the CPU awake for the length of one sample.
     *
     * A foreground service stops the process being killed. It does not stop the
     * processor suspending once the screen is off, and that is a different
     * problem. The location callback arrives on the main looper while the
     * system briefly holds its own wake lock, hands the work to a background
     * thread and returns — at which point nothing is holding the device awake
     * and the sample may not have started, let alone finished. Radio scan,
     * signing and database write are quick; a throughput test is a quarter of a
     * megabyte over a slow link and can take twenty seconds.
     *
     * So the lock is taken on the callback thread, before the system releases
     * its own, and released when the sample is done. Per sample rather than for
     * the whole session: between fixes there is nothing to keep awake, and a
     * collector's phone has to last a working day.
     */
    private val wakeLock: android.os.PowerManager.WakeLock by lazy {
        getSystemService(android.os.PowerManager::class.java)
            .newWakeLock(android.os.PowerManager.PARTIAL_WAKE_LOCK, "aipnicmp:sample")
            .apply { setReferenceCounted(false) }
    }

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val fix = result.lastLocation ?: return

            // Timed out as a safety net, not as a schedule: if a sample ever
            // hangs, the lock expires instead of holding the processor awake
            // until the battery is flat. Comfortably longer than the slowest
            // throughput test.
            wakeLock.acquire(WAKE_LOCK_TIMEOUT_MILLIS)
            try {
                work.execute {
                    try {
                        onLocation(fix)
                    } finally {
                        if (wakeLock.isHeld) wakeLock.release()
                    }
                }
            } catch (error: java.util.concurrent.RejectedExecutionException) {
                // The executor is shutting down with the service; nothing will
                // run the task, so nothing will release the lock.
                if (wakeLock.isHeld) wakeLock.release()
                Log.w(TAG, "sample dropped, collection is stopping", error)
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        store = MeasurementStore(this)
        prefs = CollectorPrefs(this)
        radio = RadioSampler(this)
        location = LocationServices.getFusedLocationProviderClient(this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopCollecting()
                return START_NOT_STICKY
            }
            else -> startCollecting()
        }
        // START_STICKY: if the system kills the service under memory pressure
        // mid-journey, collection should resume rather than silently stop and
        // leave a gap in the map that looks like a surveyed road.
        return START_STICKY
    }

    private fun startCollecting() {
        startForeground(NOTIFICATION_ID, buildNotification(store.count()))
        isRunning = true
        prefs.collectionEnabled = true
        requestLocationUpdates()
        broadcastState()
    }

    private fun stopCollecting() {
        location.removeLocationUpdates(locationCallback)
        isRunning = false
        prefs.collectionEnabled = false
        broadcastState()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    @SuppressLint("MissingPermission")
    private fun requestLocationUpdates() {
        // High accuracy, meaning GPS — not the balanced-power mode, which
        // derives a position from wifi and cell towers.
        //
        // Two reasons, and the first is fatal on its own:
        //
        //  1. A network-derived fix is unavailable in exactly the places this
        //     project exists to measure. Where there is no cell and no wifi
        //     there is nothing to derive a position from — but GPS still works,
        //     because it only listens to satellites.
        //
        //  2. Those fixes can be catastrophically wrong. Wifi databases contain
        //     access points that have physically moved, sometimes between
        //     countries, and a stale entry places the phone thousands of
        //     kilometres away. Field testing produced exactly that: half the
        //     readings landed outside Lao PDR and the server refused them.
        //
        // A coverage map built on network-derived positions would attribute
        // readings to the wrong village, which is worse than no reading at all.
        // GPS costs more battery; a wrong position costs more than that.
        // Ten seconds between fixes, not thirty.
        //
        // Proposal 2.3 asks for a record every 100 m. At 80 km/h that is every
        // 4.5 seconds, and a thirty-second interval delivered one fix every
        // 670 m — wider than a hexagon, so a drive laid down roughly one
        // reading per hexagon and skipped the ones where the road clipped a
        // corner. A ribbon with holes in it, and every tile in it flagged low
        // confidence for resting on a single reading.
        //
        // At ten seconds the same drive gives about four readings per hexagon
        // and no gaps. Sampler still enforces the 100 m rule, so a phone in
        // traffic or standing still does not multiply its records; only a
        // moving one gets the extra detail, which is the case that needed it.
        //
        // It costs battery: the receiver is asked three times as often. A day
        // of driving wants a car charger either way, and a sparse map of a
        // country is worth less than a dense map of one province.
        //
        // No displacement filter here. Sampler decides.
        //
        // This used to carry setMinUpdateDistanceMeters(50f), which tells the
        // provider to withhold any fix taken within 50 m of the last one. A
        // stationary phone therefore received no callbacks at all, and a
        // callback is the only thing that starts a reading — so a collector
        // parked in a village recorded nothing for as long as they stayed
        // there.
        //
        // That is backwards for this project. Sitting still in a place with no
        // service is not an absence of evidence, it is the evidence: proposal
        // 2.3 asks for a record every 100 m *or* every 60 seconds, and Sampler
        // implements exactly that, with its own comment saying the time branch
        // exists so a slow walk through a dead zone still produces something.
        // The provider was quietly preventing that branch from ever running.
        //
        // Sampler still refuses duplicates, so nothing floods the queue; the
        // decision simply moves to the layer that can be unit-tested.
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 10_000L)
            .setMinUpdateIntervalMillis(5_000L)
            // Wait for a real fix rather than handing back a coarse one first.
            .setWaitForAccurateLocation(true)
            .build()

        try {
            location.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
        } catch (error: SecurityException) {
            Log.e(TAG, "location permission was revoked while collecting", error)
            stopCollecting()
        }
    }

    private fun onLocation(fix: Location) {
        val now = System.currentTimeMillis()
        if (!sampler.shouldSample(fix.latitude, fix.longitude, now)) return

        // A fix this coarse is network-derived rather than satellite-derived,
        // and cannot be trusted to be in the right province, let alone the
        // right hexagon. 50 m is comfortably finer than the ~700 m hexagons
        // the data aggregates into, so nothing useful is lost by refusing it.
        if (!fix.hasAccuracy() || fix.accuracy > MAX_ACCURACY_METRES) return

        // A cached fix from before the phone moved would put this reading in
        // the wrong place. Android hands out the last known location freely;
        // a measurement needs one taken now.
        if (now - fix.time > MAX_FIX_AGE_MILLIS) return

        val snapshot = radio.sample()
        val speed = maybeMeasureSpeed(snapshot, android.os.SystemClock.elapsedRealtime())
        val measurement = try {
            sampler.buildSigned(fix, snapshot, now, speed)
        } catch (error: Exception) {
            // Signing failed — a cleared Keystore, most likely. Recording
            // unsigned records would be worse than recording none, since the
            // server would reject every one of them.
            Log.e(TAG, "could not sign measurement", error)
            return
        }

        val payload = measurement.toJson(la.aipnicmp.collector.crypto.CanonicalMessage.formatTimestamp(now))
        // Recorded now, not at upload: by the time a record is sent the phone
        // is online by definition, and the fact worth keeping is whether this
        // reading came from a place with no internet at all.
        val offline = !NetworkStatus.isOnline(this)

        if (store.enqueue(measurement, payload, offline)) {
            sampler.markSampled(fix.latitude, fix.longitude, now)
            recordedThisSession++
            updateNotification()
            broadcastState()

            // Ask WorkManager to try an upload. It carries a CONNECTED
            // constraint, so in a dead zone this simply queues and costs
            // nothing — which is the entire store-and-forward design.
            UploadScheduler.requestUpload(this)
        }
    }

    /**
     * Run a throughput test, if this is one of the rare moments it is worth it.
     *
     * Refuses far more often than it agrees, and every condition below is a
     * reason a reading would have been misleading rather than merely expensive:
     *
     * - not registered, or no usable data path: there is nothing to measure,
     *   and a failed transfer is not a slow one;
     * - not on cellular: over wifi this measures somebody's router and files
     *   the answer against a hexagon as though a tower produced it;
     * - budget spent: this is the only thing the app does that costs the
     *   collector money, so the ceiling is hard rather than advisory.
     *
     * Proposal 2.3 needs enough paired readings to learn the relationship
     * between radio conditions and real throughput. The schedule is what
     * decides how many of those a day produces, and the daily budget is what
     * stops it costing more than it is worth.
     */
    private fun maybeMeasureSpeed(
        snapshot: RadioSampler.RadioSnapshot,
        elapsedMillis: Long,
    ): SpeedTest.Result? {
        val due = lastSpeedTestAtMillis == 0L ||
            elapsedMillis - lastSpeedTestAtMillis >= SPEED_TEST_INTERVAL_MILLIS
        if (!due) return null
        if (!snapshot.registered) return null
        // isCellular requires a validated internet path, so an offline phone
        // never gets this far: no request is made, no battery spent, no bytes
        // charged. A test needs a working connection by definition — there is
        // nothing to measure without one.
        if (!NetworkStatus.isCellular(this)) return null
        if (!prefs.speedTestAllowed()) return null

        // Nor while a backlog is still going out.
        //
        // The moment a collector comes back into coverage is exactly when a
        // test was most likely to fire — the interval has long since elapsed —
        // and it is the worst moment for one. The signal is at its weakest at
        // the edge of coverage, so the figure would be the least representative
        // reading of the day, and the quarter of a megabyte it pulls down
        // competes with the queue of real measurements trying to get out.
        // Those records are the point; a throughput sample is not.
        //
        // A handful is not a backlog: one record still in flight from the last
        // sample should not postpone a test that only comes round every twelve
        // minutes.
        if (store.count() > MAX_QUEUE_FOR_SPEED_TEST) return null

        // Stamped before the run, not after: a test on a bad link can take
        // twenty seconds, and timing the gap from the end would let a slow
        // network schedule itself more often than a fast one.
        lastSpeedTestAtMillis = elapsedMillis
        val result = SpeedTest.run(prefs.apiBaseUrl)
        // Charged with what actually crossed the wire, including a run that
        // died halfway: the collector paid for those bytes either way.
        prefs.chargeSpeedTest(result.bytesUsed)
        return result.takeIf { it.downloadKbps != null || it.latencyMs != null }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.channel_collection),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.channel_collection_description)
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(queued: Int): Notification {
        val open = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stop = PendingIntent.getService(
            this, 1,
            Intent(this, CollectionService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text, recordedThisSession, queued))
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(open)
            .addAction(0, getString(R.string.action_stop), stop)
            .build()
    }

    private fun updateNotification() {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(store.count()))
    }

    private fun broadcastState() {
        sendBroadcast(Intent(ACTION_STATE_CHANGED).setPackage(packageName))
    }

    override fun onDestroy() {
        location.removeLocationUpdates(locationCallback)
        // Shut down, not shutdownNow: a throughput test in flight has already
        // spent the collector's data, so letting it finish and be charged is
        // cheaper than killing it and paying for the same bytes again.
        work.shutdown()
        // The in-flight sample releases its own lock when it finishes. This is
        // for the case where the service is destroyed between acquiring and
        // running — a held lock outliving the service that took it is how an
        // app ends up blamed for overnight battery drain.
        if (wakeLock.isHeld) wakeLock.release()
        isRunning = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
