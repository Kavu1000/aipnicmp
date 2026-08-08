package la.aipnicmp.collector.upload

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import la.aipnicmp.collector.CollectorPrefs
import la.aipnicmp.collector.data.MeasurementStore
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Uploads the queue when the phone has a network again.
 *
 * The `NetworkType.CONNECTED` constraint is what makes store-and-forward work
 * without any polling: in a dead zone the work simply does not run, costing no
 * battery and no wakeups, and the moment coverage returns the system starts it.
 */
class UploadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "UploadWorker"

        /**
         * Records per request. Small enough to finish on one bar of signal at
         * the edge of a village, large enough that a long backlog drains in a
         * reasonable number of round trips.
         */
        private const val BATCH_SIZE = 250

        /** Batches per run, so one execution can drain a substantial backlog. */
        private const val MAX_BATCHES_PER_RUN = 8
    }

    override suspend fun doWork(): Result {
        val prefs = CollectorPrefs(applicationContext)
        val installId = prefs.installId
        if (installId == null || !prefs.enrolled) {
            Log.w(TAG, "not enrolled yet; nothing to upload")
            return Result.success()
        }

        val store = MeasurementStore(applicationContext)
        val api = ApiClient(prefs.apiBaseUrl)

        var uploaded = 0
        repeat(MAX_BATCHES_PER_RUN) {
            val queued = store.peekBatch(BATCH_SIZE)
            if (queued.isEmpty()) return finish(prefs, uploaded)

            val result = api.uploadBatch(
                installId = installId,
                batchId = "and-" + UUID.randomUUID().toString().replace("-", "").take(20),
                payloads = queued.map { it.payload },
                uploadLat = prefs.lastKnownLat,
                uploadLon = prefs.lastKnownLon,
            )

            if (!result.ok) {
                store.markAttempted(queued.map { it.id })
                Log.w(TAG, "upload failed: ${result.error}")
                // A permanent failure — not enrolled, blocked — must not spin.
                // Someone has to look at it, and retrying wastes the battery of
                // a phone that may be far from a charger.
                return if (result.retryable) Result.retry() else Result.failure()
            }

            // Accepted, duplicate and rejected all mean "the server is done with
            // this record". Every rejection reason is permanent — a bad
            // signature or an impossible position will not become valid later —
            // so keeping them would block the queue behind rows that can never
            // succeed.
            store.delete(queued.map { it.id })
            uploaded += result.accepted
            prefs.recordUploadResult(result.accepted, result.rejectedIds.size)

            if (result.rejectedIds.isNotEmpty()) {
                Log.w(TAG, "server rejected ${result.rejectedIds.size}: ${result.rejectionReasons.distinct()}")
            }
            if (queued.size < BATCH_SIZE) return finish(prefs, uploaded)
        }

        return finish(prefs, uploaded)
    }

    private fun finish(prefs: CollectorPrefs, uploaded: Int): Result {
        if (uploaded > 0) prefs.lastUploadAtMillis = System.currentTimeMillis()
        return Result.success()
    }
}

object UploadScheduler {

    private const val ONE_OFF = "upload-now"
    private const val PERIODIC = "upload-periodic"

    private val constraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /**
     * Ask for an upload attempt. Cheap to call after every record: WorkManager
     * keeps the existing request rather than queueing a second one.
     */
    fun requestUpload(context: Context) {
        val request = OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 5, TimeUnit.MINUTES)
            .build()

        WorkManager.getInstance(context)
            .enqueueUniqueWork(ONE_OFF, ExistingWorkPolicy.KEEP, request)
    }

    /**
     * A safety net for the phone that regains coverage while the app is not
     * running — the ordinary case for a collector who reaches town with the
     * screen off.
     */
    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<UploadWorker>(2, TimeUnit.HOURS)
            .setConstraints(constraints)
            .build()

        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
    }
}
