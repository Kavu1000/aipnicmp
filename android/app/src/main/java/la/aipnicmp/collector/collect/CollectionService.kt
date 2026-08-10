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
         * Samples between throughput tests. At 30s sampling this is roughly one
         * test every twelve minutes of active collecting — sparse enough to be
         * affordable, frequent enough to gather paired readings across a day's
         * drive.
         */
        private const val SAMPLES_BETWEEN_SPEED_TESTS = 25

        /** Above this, the fix came from wifi or cell towers rather than GPS. */
        private const val MAX_ACCURACY_METRES = 50f

        /** Older than this and the phone may have moved since the fix was taken. */
        private const val MAX_FIX_AGE_MILLIS = 90_000L

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

    /** Samples since the last throughput test, counting the sparse schedule. */
    private var samplesSinceSpeedTest = SAMPLES_BETWEEN_SPEED_TESTS

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let { fix -> work.execute { onLocation(fix) } }
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
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 30_000L)
            .setMinUpdateIntervalMillis(10_000L)
            .setMinUpdateDistanceMeters(50f)
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
        val speed = maybeMeasureSpeed(snapshot)
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
     * The sparse schedule is the point. Proposal 2.3 needs enough paired
     * readings to learn the relationship between radio conditions and real
     * throughput — a few dozen a day across varied terrain does that. One per
     * sample would spend a collector's bundle to learn almost nothing extra.
     */
    private fun maybeMeasureSpeed(snapshot: RadioSampler.RadioSnapshot): SpeedTest.Result? {
        samplesSinceSpeedTest++
        if (samplesSinceSpeedTest < SAMPLES_BETWEEN_SPEED_TESTS) return null
        if (!snapshot.registered) return null
        if (!NetworkStatus.isCellular(this)) return null
        if (!prefs.speedTestAllowed()) return null

        samplesSinceSpeedTest = 0
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
        isRunning = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
