package la.aipnicmp.collector.collect

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import la.aipnicmp.collector.CollectorPrefs
import la.aipnicmp.collector.upload.UploadScheduler

/**
 * Resumes collection after a reboot, but only if it was running beforehand.
 *
 * Partner collectors — a bus driver, a health worker on a field visit — carry
 * the phone for days. A flat battery overnight should not silently end the
 * survey and leave a gap in the map that reads as "we drove this road and found
 * nothing to report".
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        val prefs = CollectorPrefs(context)
        UploadScheduler.schedulePeriodic(context)

        if (prefs.collectionEnabled && prefs.enrolled) {
            CollectionService.start(context)
        }
    }
}
