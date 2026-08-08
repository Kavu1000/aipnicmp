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

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let { onLocation(it) }
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
        // Balanced power rather than high accuracy: a 10-20 m fix is far finer
        // than the ~700 m hexagons the data is aggregated into, and battery is
        // what decides whether a volunteer keeps the app installed.
        val request = LocationRequest.Builder(Priority.PRIORITY_BALANCED_POWER_ACCURACY, 30_000L)
            .setMinUpdateIntervalMillis(15_000L)
            .setMinUpdateDistanceMeters(50f)
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

        // A fix this coarse is usually network-derived, which cannot be true
        // where there is no network — and the server would reject it anyway.
        if (fix.accuracy > 100f) return

        val snapshot = radio.sample()
        val measurement = try {
            sampler.buildSigned(fix, snapshot, now)
        } catch (error: Exception) {
            // Signing failed — a cleared Keystore, most likely. Recording
            // unsigned records would be worse than recording none, since the
            // server would reject every one of them.
            Log.e(TAG, "could not sign measurement", error)
            return
        }

        val payload = measurement.toJson(la.aipnicmp.collector.crypto.CanonicalMessage.formatTimestamp(now))
        if (store.enqueue(measurement, payload)) {
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
        isRunning = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
