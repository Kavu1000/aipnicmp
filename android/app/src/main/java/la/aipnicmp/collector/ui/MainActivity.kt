package la.aipnicmp.collector.ui

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import android.graphics.Typeface
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.ImageView
import android.widget.ListPopupWindow
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import la.aipnicmp.collector.BuildConfig
import la.aipnicmp.collector.CollectorPrefs
import la.aipnicmp.collector.R
import la.aipnicmp.collector.collect.CollectionService
import la.aipnicmp.collector.collect.RadioSampler
import la.aipnicmp.collector.crypto.DeviceKeystore
import android.net.ConnectivityManager
import la.aipnicmp.collector.data.MeasurementStore
import la.aipnicmp.collector.data.NetworkStatus
import la.aipnicmp.collector.databinding.ActivityMainBinding
import android.content.res.ColorStateList
import la.aipnicmp.collector.upload.ApiClient
import la.aipnicmp.collector.upload.ApiClient.ConnectionCode
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
/**
 * How recently an upload must have succeeded for the phone to still count as
 * getting records out. Comfortably longer than the sampling interval, so a
 * quiet moment between records does not flip the mode line to offline.
 */
private const val RECENT_UPLOAD_MILLIS = 5 * 60 * 1000L

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: CollectorPrefs
    private lateinit var store: MeasurementStore

    /**
     * Reads the radio for the network shown on screen — the same sampler the
     * collection service uses, so what a collector sees is what gets recorded
     * rather than a second opinion.
     */
    private val radio: RadioSampler by lazy { RadioSampler(this) }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) = refresh()
    }

    private val requestForeground = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted[Manifest.permission.ACCESS_FINE_LOCATION] == true) {
            requestBackgroundLocation()
            // Granting location is the answer to "may this phone survey?", so
            // the survey starts. Asking someone to grant the permission and
            // then press a button to use it is asking the same question twice,
            // and on a phone handed to a partner the second question is the one
            // that never gets answered.
            enrolThenStart()
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

        wireUp()
        refresh()
    }

    /**
     * Everything the freshly inflated views need. Called again after a language
     * change, because that reinflates them.
     */
    private fun wireUp() {
        binding.serverValue.setText(prefs.apiBaseUrl)
        // Long press, not a visible control: the people carrying this phone
        // should never need it, and whoever is running the pilot will be told.
        binding.serverDisplay.setOnLongClickListener {
            binding.serverAdvanced.visibility = View.VISIBLE
            showMessage(getString(R.string.server_unlocked))
            true
        }
        binding.saveServerButton.setOnClickListener { onSaveServer() }
        binding.checkConnectionButton.setOnClickListener { onCheckConnection() }
        binding.resetServerButton.setOnClickListener { onResetServer() }
        binding.languageChip.setOnClickListener { showLanguageMenu() }
        binding.toggleButton.setOnClickListener { onToggle() }
        binding.recordsButton.setOnClickListener {
            startActivity(Intent(this, RecordsActivity::class.java))
        }
        binding.uploadButton.setOnClickListener {
            UploadScheduler.requestUpload(this)
            showMessage(getString(R.string.upload_requested))
        }

        showLanguage()
    }

    override fun onResume() {
        super.onResume()
        ContextCompat.registerReceiver(
            this,
            stateReceiver,
            IntentFilter(CollectionService.ACTION_STATE_CHANGED),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        // Watched rather than read once: a collector leaving town wants the
        // screen to say so as it happens, not when they next reopen the app.
        networkCallback = NetworkStatus.observe(this) { runOnUiThread { refresh() } }
        resumeCollectionIfWanted()
        refresh()
    }

    /**
     * Start collecting without anyone pressing anything.
     *
     * A phone handed to a bus driver or a health worker should be carrying out
     * a survey, not waiting to be asked. Once enrolled it collects whenever the
     * app is opened, exactly as it does after a reboot — BootReceiver has
     * always worked this way, and opening the app should not be a weaker
     * trigger than switching the phone on.
     *
     * Stop still means stop. The flag this reads is cleared when the button is
     * pressed and set when collection starts, so a deliberate stop survives
     * both a reopen and a reboot; otherwise the button would undo itself the
     * next time the screen was unlocked, which is worse than having no button.
     *
     * Permissions are the one thing that cannot be assumed. Android grants them
     * to a person, not to a configuration file, so a phone that has never been
     * granted location shows the warning and waits rather than failing to start
     * a service it is not allowed to run.
     */
    private fun resumeCollectionIfWanted() {
        if (CollectionService.isRunning) return
        if (!prefs.collectionEnabled || !prefs.enrolled) return
        if (!hasForegroundLocation()) return
        CollectionService.start(this)
    }

    override fun onPause() {
        super.onPause()
        runCatching { unregisterReceiver(stateReceiver) }
        NetworkStatus.stopObserving(this, networkCallback)
        networkCallback = null
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

    /**
     * Return to the address this build ships with.
     *
     * The recovery path when a phone is pointed at a server that has moved or
     * never existed. Without it the only remedy is reinstalling, which throws
     * away the queue of records the device is holding — the very data that
     * cannot be collected again.
     */
    private fun onResetServer() {
        if (CollectionService.isRunning) {
            showMessage(getString(R.string.error_server_while_running))
            return
        }
        prefs.resetApiBaseUrl()
        prefs.enrolled = false
        binding.serverValue.setText(prefs.apiBaseUrl)
        showMessage(getString(R.string.server_reset, prefs.apiBaseUrl))
        refresh()
    }

    /**
     * Answer "is this phone actually talking to the server" directly.
     *
     * Without it the only signals are counters, and "Sent 0 / Last upload
     * Never" looks identical whether the address is wrong, the device was never
     * registered, or nothing has been recorded yet. Someone carrying this phone
     * up a mountain road deserves to know before they set off, not after.
     */
    private fun onCheckConnection() {
        binding.checkConnectionButton.isEnabled = false
        binding.connectionValue.setText(R.string.connection_checking)
        binding.connectionValue.setTextColor(getColor(R.color.muted))
        binding.connectionDot.backgroundTintList = ColorStateList.valueOf(getColor(R.color.muted))
        binding.connectionDetail.text = ""

        lifecycleScope.launch {
            val status = withContext(Dispatchers.IO) {
                val hardwareBacked = runCatching { DeviceKeystore.ensureKey() }.getOrDefault(false)
                ApiClient(prefs.apiBaseUrl).checkConnection(
                    installId = prefs.ensureInstallId(),
                    appVersion = BuildConfig.VERSION_NAME,
                    hardwareBacked = hardwareBacked,
                )
            }

            // A successful check has already registered the device, so record
            // that rather than making the user press Start to find out.
            if (status.enrolled) prefs.enrolled = true

            binding.checkConnectionButton.isEnabled = true
            showConnection(status)
            refresh()
        }
    }

    /**
     * Say the outcome in the reader's language, and colour it.
     *
     * Green, amber and red carry the meaning faster than any sentence, and they
     * are the same three colours the map uses for working, degraded and absent
     * — someone who has read the map already knows what they mean.
     */
    private fun showConnection(status: ApiClient.ConnectionStatus) {
        val (message, colour) = when (status.code) {
            ConnectionCode.CONNECTED -> R.string.connection_ok to R.color.good
            ConnectionCode.NOT_REGISTERED ->
                R.string.connection_reachable_not_enrolled to R.color.calls_only
            ConnectionCode.KEY_CONFLICT -> R.string.connection_key_conflict to R.color.calls_only
            ConnectionCode.UNREACHABLE -> R.string.connection_failed to R.color.primary
        }

        binding.connectionValue.setText(message)
        binding.connectionValue.setTextColor(getColor(colour))
        binding.connectionDot.backgroundTintList = ColorStateList.valueOf(getColor(colour))

        val checked = getString(
            R.string.connection_checked_at,
            DateFormat.getTimeInstance(DateFormat.SHORT).format(Date()),
        )
        // The technical detail is only shown when something went wrong. On
        // success it would repeat the headline in the wrong language.
        binding.connectionDetail.text =
            if (status.code == ConnectionCode.CONNECTED || status.detail.isNullOrBlank()) {
                checked
            } else {
                "$checked · ${status.detail}"
            }
    }

    /**
     * The languages this app ships, in the order the menu lists them.
     *
     * Each name is written in its own script rather than translated, because
     * the person who needs this control is by definition looking at a language
     * they may not read.
     */
    private val languages = listOf(
        Triple("en", R.string.language_english, R.drawable.flag_en),
        Triple("lo", R.string.language_lao, R.drawable.flag_lo),
    )

    /** The tag in force, whether chosen here or inherited from the phone. */
    private fun currentLanguage(): String =
        AppCompatDelegate.getApplicationLocales().takeIf { !it.isEmpty }?.get(0)?.language
            ?: resources.configuration.locales[0].language

    /**
     * The language menu, in the shape the dashboard uses: a flag and the
     * language's own name, one row each.
     */
    private fun showLanguageMenu() {
        val popup = ListPopupWindow(this)
        popup.anchorView = binding.languageChip
        popup.isModal = true
        popup.width = resources.getDimensionPixelSize(R.dimen.language_menu_width)
        popup.setAdapter(object : BaseAdapter() {
            override fun getCount() = languages.size
            override fun getItem(position: Int) = languages[position]
            override fun getItemId(position: Int) = position.toLong()
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                val row = convertView ?: layoutInflater.inflate(R.layout.item_language, parent, false)
                val (tag, label, flag) = languages[position]
                row.findViewById<ImageView>(R.id.itemFlag).setImageResource(flag)
                row.findViewById<TextView>(R.id.itemName).apply {
                    setText(label)
                    // Weight, not a tick: a tick column would indent every row
                    // to make room for a mark on one of them.
                    setTypeface(null, if (tag == currentLanguage()) Typeface.BOLD else Typeface.NORMAL)
                }
                return row
            }
        })
        popup.setOnItemClickListener { _, _, position, _ ->
            popup.dismiss()
            setLanguage(languages[position].first)
        }
        popup.show()
    }

    /**
     * Switch the app's language without touching the phone's, and without
     * rebuilding the screen.
     *
     * A collector is often handed a device configured by someone else, and
     * changing the whole phone to read one app is not a reasonable thing to
     * ask. The choice is persisted by AppCompat, so it survives a restart and
     * applies to the records screen too.
     *
     * The activity declares locale in its configChanges, so AppCompat delivers
     * onConfigurationChanged instead of destroying and rebuilding it. Nothing
     * blanks, the scroll position holds, and a live count keeps counting — the
     * language changes and nothing else moves.
     */
    private fun setLanguage(tag: String) {
        if (tag == currentLanguage()) return
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))
    }

    /**
     * Re-read the layout in the new language, without rebuilding the activity.
     *
     * The layout is inflated again rather than each label being set by hand.
     * Twelve of the fixed labels on this screen carry no id, and a list of
     * setText calls is a list that silently stops covering anything added to
     * the layout later — the new label would just stay in the old language.
     * Reinflating cannot drift.
     *
     * The activity itself survives, which is the point: the collection service
     * is never touched, the window is never torn down, and the scroll position
     * is carried across so the screen does not jump back to the top.
     */
    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        val scrolled = binding.root.scrollY
        val advancedShown = binding.serverAdvanced.visibility

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        wireUp()
        binding.serverAdvanced.visibility = advancedShown
        refresh()
        binding.root.post { binding.root.scrollTo(0, scrolled) }
    }

    /** Shows which language is in force, on the chip itself. */
    private fun showLanguage() {
        val current = currentLanguage()
        val (_, label, flag) = languages.firstOrNull { it.first == current } ?: languages[0]
        binding.languageFlag.setImageResource(flag)
        binding.languageName.setText(label)
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

        // What is happening to the records, not what a capability flag says
        // this instant.
        //
        // This line used to be NetworkStatus.isOnline() alone, which requires
        // NET_CAPABILITY_VALIDATED. Android drops that during revalidation, a
        // cell handover or a dual-SIM switch while data keeps working, so the
        // screen announced "Offline - records are being kept on this phone"
        // above a queue of zero, twenty-four sent, and an upload four minutes
        // earlier. Every figure on the card contradicted the one word above
        // them.
        //
        // A collector reads this to learn whether their work is getting out.
        // The queue and the last upload answer that directly, so they decide
        // it: anything waiting means the phone is holding records, and a
        // successful upload in the last few minutes means it is not, whatever
        // the flag says between one probe and the next.
        val uploadedRecently =
            prefs.lastUploadAtMillis > 0 &&
                System.currentTimeMillis() - prefs.lastUploadAtMillis < RECENT_UPLOAD_MILLIS
        val gettingOut = queued == 0 && (NetworkStatus.isOnline(this) || uploadedRecently)

        binding.modeValue.setText(if (gettingOut) R.string.mode_online else R.string.mode_offline)
        binding.modeValue.setTextColor(
            getColor(if (gettingOut) R.color.good else R.color.calls_only)
        )

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

        // Shown rather than editable. A collector who has to phone for help
        // should be able to read out where the app is pointing.
        showLanguage()

        binding.serverDisplay.text = prefs.apiBaseUrl
        binding.serverDisplay.setTextColor(
            getColor(if (prefs.apiBaseUrlIsCustom) R.color.calls_only else R.color.muted)
        )

        showPermissionWarning()
        showBatteryWarning()
        showNetwork()
    }

    /**
     * The network this phone is attached to, as the modem reports it.
     *
     * Every reading is filed under this, so a phone carrying the wrong SIM
     * collects for the wrong operator all day before anyone notices. It was
     * only visible by opening an individual record, which is not where anybody
     * would think to check.
     *
     * Shows the operator's own name with the PLMN beside it. The name comes
     * from the SIM and varies between handsets — "LTC" on one, "LAO TELECOM"
     * on another — so the code is what the platform actually identifies the
     * network by, and seeing both is what makes a mismatch obvious.
     */
    private fun showNetwork() {
        if (!hasForegroundLocation()) {
            binding.networkValue.setText(R.string.network_no_permission)
            return
        }

        val snapshot = radio.sample()
        val plmn = listOfNotNull(snapshot.mcc, snapshot.mnc)
            .takeIf { it.size == 2 }
            ?.joinToString("-")
        val name = snapshot.operatorName

        binding.networkValue.text = when {
            name != null && plmn != null -> "$name · $plmn"
            name != null -> name
            plmn != null -> plmn
            // No name and no code: the modem is not attached to anything. Not
            // an error — it is the finding this whole app exists to collect.
            else -> getString(R.string.network_none)
        }
    }

    /**
     * Battery optimisation is what actually stops overnight collection.
     *
     * Doze and App Standby defer precisely what this app does, and several
     * vendor ROMs stop foreground services outright whatever Android's own
     * rules say. A collector handed a phone for a week has no way to know any
     * of that; they only see a map with a day missing from it.
     *
     * Asked, never forced: the system dialog is the user's decision, and
     * collection still works without it — just less reliably once the screen is
     * off. The warning disappears the moment it is granted.
     */
    private fun showBatteryWarning() {
        if (isIgnoringBatteryOptimisation()) {
            binding.batteryWarning.visibility = android.view.View.GONE
            return
        }

        binding.batteryWarning.visibility = android.view.View.VISIBLE
        binding.batteryWarning.setOnClickListener { requestBatteryExemption() }
    }

    private fun isIgnoringBatteryOptimisation(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        return getSystemService(android.os.PowerManager::class.java)
            ?.isIgnoringBatteryOptimizations(packageName) ?: true
    }

    @android.annotation.SuppressLint("BatteryLife")
    private fun requestBatteryExemption() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return

        val ask = Intent(
            android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            android.net.Uri.fromParts("package", packageName, null),
        )
        try {
            startActivity(ask)
        } catch (_: android.content.ActivityNotFoundException) {
            // Some ROMs remove the direct dialog. The battery settings list is
            // a longer road to the same switch, and better than a dead tap.
            try {
                startActivity(Intent(android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (_: android.content.ActivityNotFoundException) {
                openAppSettings()
            }
        }
    }

    /**
     * Say which permission is missing, and give a way to grant it.
     *
     * These are two different problems. Without foreground location the phone
     * cannot see cells at all; with it, but without background location,
     * everything works until the screen goes off. One warning covering both
     * told collectors who had granted foreground location that their phone
     * could not read signal strength — which was untrue, and left them with
     * nothing to do about it either.
     *
     * The remedy differs too. Foreground location can still be asked for in a
     * dialog. "Allow all the time" cannot, from Android 11 onwards: the system
     * shows no prompt for it, and the only route is the app's own settings
     * page. So the warning opens that page.
     */
    private fun showPermissionWarning() {
        val foreground = hasForegroundLocation()
        val background = hasBackgroundLocation()

        if (foreground && background) {
            binding.permissionWarning.visibility = android.view.View.GONE
            return
        }

        binding.permissionWarning.visibility = android.view.View.VISIBLE
        binding.permissionWarning.setText(
            if (foreground) R.string.warning_background_location else R.string.warning_permissions
        )
        binding.permissionWarning.setOnClickListener {
            if (!foreground) requestPermissions() else openAppSettings()
        }
    }

    /**
     * The app's own page in Settings, which is where "Allow all the time"
     * lives. Falls back to the full settings list on a device whose launcher
     * does not answer the direct intent — rare, but a dead button in a warning
     * is worse than one extra tap.
     */
    private fun openAppSettings() {
        val direct = Intent(
            android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            android.net.Uri.fromParts("package", packageName, null),
        )
        try {
            startActivity(direct)
        } catch (_: android.content.ActivityNotFoundException) {
            try {
                startActivity(Intent(android.provider.Settings.ACTION_SETTINGS))
            } catch (_: android.content.ActivityNotFoundException) {
                showMessage(getString(R.string.warning_background_location))
            }
        }
    }

    private fun showMessage(message: String) {
        AlertDialog.Builder(this)
            .setMessage(message)
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }
}
