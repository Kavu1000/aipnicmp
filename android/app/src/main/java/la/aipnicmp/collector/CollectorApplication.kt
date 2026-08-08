package la.aipnicmp.collector

import android.app.Application
import la.aipnicmp.collector.upload.UploadScheduler

class CollectorApplication : Application() {

    override fun onCreate() {
        super.onCreate()
        // Registered on every launch: the periodic worker is what catches a
        // phone that reaches town with the screen off, which is how most
        // uploads from a real collection journey will actually happen.
        UploadScheduler.schedulePeriodic(this)
    }
}
