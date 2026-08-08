package la.aipnicmp.collector.ui

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import la.aipnicmp.collector.BuildConfig
import la.aipnicmp.collector.CollectorPrefs
import la.aipnicmp.collector.R
import la.aipnicmp.collector.collect.CollectionService
import la.aipnicmp.collector.crypto.DeviceKeystore
import la.aipnicmp.collector.data.MeasurementStore
import la.aipnicmp.collector.databinding.ActivityMainBinding
import la.aipnicmp.collector.upload.ApiClient
import la.aipnicmp.collector.upload.UploadScheduler
import java.text.DateFormat
import java.util.Date

/**
 * The whole UI: what the app is doing, and one button to start or stop it.
 *
 * Deliberately plain. The person carrying this phone is driving a bus or
 * visiting a clinic, not administering a survey, so the screen answers only the
 * questions they will actually have — is it recording, how much is waiting to
 * send, and did anything reach the server.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: CollectorPrefs
    private lateinit var store: MeasurementStore

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) = refresh()
    }

    private val requestForeground = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted[Manifest.permission.ACCESS_FINE_LOCATION] == true) {
            requestBackgroundLocation()
        } else {
            showMessage(getString(R.string.error_location_required))
        }
        refresh()
    }

    private val requestBackground = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { refresh() }

    private val requestNotifications = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { refresh() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = CollectorPrefs(this)
        store = MeasurementStore(this)

        binding.serverValue.setText(prefs.apiBaseUrl)
        binding.saveServerButton.setOnClickListener { onSaveServer() }
        binding.toggleButton.setOnClickListener { onToggle() }
        binding.uploadButton.setOnClickListener {
            UploadScheduler.requestUpload(this)
            showMessage(getString(R.string.upload_requested))
        }

        refresh()
    }

    override fun onResume() {
        super.onResume()
        ContextCompat.registerReceiver(
            this,
            stateReceiver,
            IntentFilter(CollectionService.ACTION_STATE_CHANGED),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        refresh()
    }

    override fun onPause() {
        super.onPause()
        runCatching { unregisterReceiver(stateReceiver) }
    }

    private fun onToggle() {
        if (CollectionService.isRunning) {
            CollectionService.stop(this)
            return
        }
        if (!hasForegroundLocation()) {
            requestPermissions()
            return
        }
        enrolThenStart()
    }

    /**
     * Enrol before the first collection, never during it.
     *
     * A record signed by a key the server has never seen is rejected as a bad
     * signature and cannot be re-signed later — the signature has to be made at
     * capture time. Recording before enrolment would quietly produce a queue of
     * permanently worthless data.
     */
    private fun enrolThenStart() {
        if (prefs.enrolled && DeviceKeystore.hasKey()) {
            CollectionService.start(this)
            return
        }

        binding.toggleButton.isEnabled = false
        binding.statusValue.text = getString(R.string.status_enrolling)

        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                val hardwareBacked = DeviceKeystore.ensureKey()
                val installId = prefs.ensureInstallId()
                ApiClient(prefs.apiBaseUrl).enroll(
                    installId = installId,
                    appVersion = BuildConfig.VERSION_NAME,
                    hardwareBacked = hardwareBacked,
                )
            }

            binding.toggleButton.isEnabled = true
            if (result.ok) {
                prefs.enrolled = true
                CollectionService.start(this@MainActivity)
            } else {
                showMessage(getString(R.string.error_enrolment, result.error.orEmpty()))
            }
            refresh()
        }
    }

    /**
     * Repoint the collector at a different backend.
     *
     * Changing the server also resets enrolment, because the new server has
     * never seen this device's public key: without re-enrolling, every upload
     * would be refused with "device is not enrolled". The queue is kept — those
     * records are signed by a key the new server will hold once enrolment
     * completes, so they remain valid evidence.
     */
    private fun onSaveServer() {
        if (CollectionService.isRunning) {
            showMessage(getString(R.string.error_server_while_running))
            return
        }

        val entered = binding.serverValue.text.toString().trim().trimEnd('/')
        if (!entered.startsWith("http://") && !entered.startsWith("https://")) {
            showMessage(getString(R.string.error_server_invalid))
            return
        }

        if (entered != prefs.apiBaseUrl) {
            prefs.apiBaseUrl = entered
            prefs.enrolled = false
        }
        binding.serverValue.setText(prefs.apiBaseUrl)
        showMessage(getString(R.string.server_saved))
        refresh()
    }

    private fun hasForegroundLocation(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private fun hasBackgroundLocation(): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            true
        } else {
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
        }

    private fun requestPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        requestForeground.launch(
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
                Manifest.permission.READ_PHONE_STATE,
            )
        )
    }

    /**
     * Background location must be a separate request, made only after fine
     * location is granted — Android 11 and later will not even show the prompt
     * otherwise. The explanation matters too: this is the permission people
     * refuse, and refusing it means the app only records while the screen is
     * on, which is almost never on a bus.
     */
    private fun requestBackgroundLocation() {
        if (hasBackgroundLocation()) return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return

        AlertDialog.Builder(this)
            .setTitle(R.string.background_title)
            .setMessage(R.string.background_message)
            .setPositiveButton(R.string.background_continue) { _, _ ->
                requestBackground.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            }
            .setNegativeButton(R.string.background_skip, null)
            .show()
    }

    private fun refresh() {
        val running = CollectionService.isRunning
        val queued = store.count()

        binding.statusValue.text = when {
            running -> getString(R.string.status_collecting)
            prefs.enrolled -> getString(R.string.status_idle)
            else -> getString(R.string.status_not_enrolled)
        }
        binding.toggleButton.setText(if (running) R.string.action_stop else R.string.action_start)

        binding.queuedValue.text = queued.toString()
        binding.sentValue.text = prefs.totalAccepted.toString()
        binding.rejectedValue.text = prefs.totalRejected.toString()

        binding.lastUploadValue.text = prefs.lastUploadAtMillis
            .takeIf { it > 0 }
            ?.let { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(it)) }
            ?: getString(R.string.never)

        // The oldest queued record is the honest measure of how long this phone
        // has been out of coverage — the thing worth showing on a survey trip.
        val oldest = store.oldestCapturedAt()
        binding.oldestValue.text = if (oldest == null) {
            getString(R.string.none)
        } else {
            val hours = (System.currentTimeMillis() - oldest) / 3_600_000L
            when {
                hours < 1 -> getString(R.string.age_under_hour)
                hours < 48 -> getString(R.string.age_hours, hours)
                else -> getString(R.string.age_days, hours / 24)
            }
        }

        binding.permissionWarning.visibility =
            if (hasForegroundLocation() && hasBackgroundLocation()) android.view.View.GONE
            else android.view.View.VISIBLE
    }

    private fun showMessage(message: String) {
        AlertDialog.Builder(this)
            .setMessage(message)
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }
}
