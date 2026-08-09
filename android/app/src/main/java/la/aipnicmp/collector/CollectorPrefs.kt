package la.aipnicmp.collector

import android.content.Context
import java.util.UUID

/**
 * Local state.
 *
 * The install id is the only identifier this app holds. It is random, generated
 * on first launch, and gone on uninstall — no account, no phone number, no
 * IMEI. Proposal 2.6 promises anonymised data, and the cheapest way to keep
 * that promise is to have nothing else to hand over.
 */
class CollectorPrefs(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("collector", Context.MODE_PRIVATE)

    init {
        forgetAddressesFromTheEditableEra()
    }

    /**
     * Clear a server address saved back when the field was on screen.
     *
     * App data survives an upgrade, so a phone that was once pointed at a
     * laptop keeps pointing there — and now that the field is hidden, its owner
     * cannot see why nothing uploads or put it right. Anything entered
     * deliberately after this build, through the long press, is kept: the
     * generation marker is written once and never rewritten.
     */
    private fun forgetAddressesFromTheEditableEra() {
        if (prefs.getInt(KEY_SETTINGS_GENERATION, 0) >= SETTINGS_GENERATION) return
        prefs.edit()
            .remove(KEY_API_URL)
            .remove(KEY_API_URL_USER_SET)
            .putInt(KEY_SETTINGS_GENERATION, SETTINGS_GENERATION)
            .apply()
    }

    /** Created on first access and never changed. */
    val installId: String?
        get() = prefs.getString(KEY_INSTALL_ID, null)

    fun ensureInstallId(): String {
        installId?.let { return it }
        val generated = "and-" + UUID.randomUUID().toString().replace("-", "")
        prefs.edit().putString(KEY_INSTALL_ID, generated).apply()
        return generated
    }

    /**
     * Start over with a new identity.
     *
     * Needed when the Keystore key is gone — a device restore, say — because
     * the server will not rotate the key for an existing install id, so the
     * only way back is to become a new device.
     */
    fun resetIdentity() {
        prefs.edit()
            .remove(KEY_INSTALL_ID)
            .putBoolean(KEY_ENROLLED, false)
            .apply()
    }

    var enrolled: Boolean
        get() = prefs.getBoolean(KEY_ENROLLED, false)
        set(value) = prefs.edit().putBoolean(KEY_ENROLLED, value).apply()

    var collectionEnabled: Boolean
        get() = prefs.getBoolean(KEY_COLLECTING, false)
        set(value) = prefs.edit().putBoolean(KEY_COLLECTING, value).apply()

    /**
     * Where to upload. Overridable in the field without a rebuild, for a pilot
     * that moves hosts.
     *
     * A stored address is honoured *only* when the user deliberately entered
     * one. Otherwise the build default wins, including after an app update —
     * app data survives an upgrade, so an address saved once would silently
     * outlive every later build and strand the phone on a server that had
     * moved. That is exactly what happened when the default changed from a
     * laptop's wifi address to the live server.
     */
    var apiBaseUrl: String
        get() {
            if (!prefs.getBoolean(KEY_API_URL_USER_SET, false)) {
                // Drop anything left by an older build so the two cannot
                // disagree later.
                if (prefs.contains(KEY_API_URL)) prefs.edit().remove(KEY_API_URL).apply()
                return BuildConfig.API_BASE_URL
            }
            return prefs.getString(KEY_API_URL, BuildConfig.API_BASE_URL) ?: BuildConfig.API_BASE_URL
        }
        set(value) {
            prefs.edit()
                .putString(KEY_API_URL, value.trimEnd('/'))
                .putBoolean(KEY_API_URL_USER_SET, true)
                .apply()
        }

    /** True when the address came from the user rather than from the build. */
    val apiBaseUrlIsCustom: Boolean
        get() = prefs.getBoolean(KEY_API_URL_USER_SET, false)

    /**
     * Go back to the address this build ships with.
     *
     * The recovery path for a phone pointed at a server that no longer exists —
     * without it the only remedy is reinstalling, which also destroys the
     * queue of records the device is holding.
     */
    fun resetApiBaseUrl() {
        prefs.edit().remove(KEY_API_URL).remove(KEY_API_URL_USER_SET).apply()
    }

    var lastUploadAtMillis: Long
        get() = prefs.getLong(KEY_LAST_UPLOAD, 0L)
        set(value) = prefs.edit().putLong(KEY_LAST_UPLOAD, value).apply()

    val totalAccepted: Int get() = prefs.getInt(KEY_TOTAL_ACCEPTED, 0)
    val totalRejected: Int get() = prefs.getInt(KEY_TOTAL_REJECTED, 0)

    fun recordUploadResult(accepted: Int, rejected: Int) {
        prefs.edit()
            .putInt(KEY_TOTAL_ACCEPTED, totalAccepted + accepted)
            .putInt(KEY_TOTAL_REJECTED, totalRejected + rejected)
            .apply()
    }

    /**
     * Where the device was when it last had a fix, sent with an upload so the
     * server can sanity-check the journey. Advisory only — a long gap between
     * capture and upload is the system working, not a red flag.
     */
    var lastKnownLat: Double?
        get() = prefs.getFloat(KEY_LAST_LAT, Float.NaN).takeIf { !it.isNaN() }?.toDouble()
        set(value) {
            prefs.edit().putFloat(KEY_LAST_LAT, value?.toFloat() ?: Float.NaN).apply()
        }

    var lastKnownLon: Double?
        get() = prefs.getFloat(KEY_LAST_LON, Float.NaN).takeIf { !it.isNaN() }?.toDouble()
        set(value) {
            prefs.edit().putFloat(KEY_LAST_LON, value?.toFloat() ?: Float.NaN).apply()
        }

    private companion object {
        /**
         * Bumped when a stored setting stops meaning what it used to. Currently
         * 1: the server address became read-only, so addresses saved under the
         * old editable field are discarded once.
         */
        const val SETTINGS_GENERATION = 1
        const val KEY_SETTINGS_GENERATION = "settings_generation"

        const val KEY_INSTALL_ID = "install_id"
        const val KEY_ENROLLED = "enrolled"
        const val KEY_COLLECTING = "collecting"
        const val KEY_API_URL = "api_base_url"
        const val KEY_API_URL_USER_SET = "api_base_url_user_set"
        const val KEY_LAST_UPLOAD = "last_upload_at"
        const val KEY_TOTAL_ACCEPTED = "total_accepted"
        const val KEY_TOTAL_REJECTED = "total_rejected"
        const val KEY_LAST_LAT = "last_lat"
        const val KEY_LAST_LON = "last_lon"
    }
}
