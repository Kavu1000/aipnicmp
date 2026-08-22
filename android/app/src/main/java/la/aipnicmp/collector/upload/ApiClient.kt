package la.aipnicmp.collector.upload

import android.os.Build
import la.aipnicmp.collector.BuildConfig
import la.aipnicmp.collector.crypto.DeviceKeystore
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Talks to the ingestion API.
 *
 * Timeouts are generous because the upload that matters most is the one made
 * from the edge of coverage, on a single bar, after days offline.
 */
class ApiClient(private val baseUrl: String = BuildConfig.API_BASE_URL) {

    private val json = "application/json; charset=utf-8".toMediaType()

    private val http = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    data class EnrollResult(val ok: Boolean, val trustLevel: String?, val error: String?)

    /**
     * What a connection check found.
     *
     * Deliberately separates "the server answered" from "the server will accept
     * my uploads". A phone can have perfect internet and still be unable to
     * contribute — wrong address, not enrolled, or enrolled under a key the
     * server no longer holds — and every one of those looks identical from the
     * outside if the only signal is a counter that never moves.
     */
    data class ConnectionStatus(
        val code: ConnectionCode,
        /**
         * Technical detail for the failure cases only — an HTTP status, or
         * whatever the network stack said. Left in English on purpose: it comes
         * from the platform, not from us, and a half-translated error is harder
         * to act on than an untranslated one. Never shown on success, where it
         * would only repeat the headline.
         */
        val detail: String? = null,
    ) {
        val reachable: Boolean get() = code != ConnectionCode.UNREACHABLE
        val enrolled: Boolean get() = code == ConnectionCode.CONNECTED
    }

    /**
     * The outcomes worth telling apart, because each needs a different remedy:
     * a wrong address, an unregistered device, and a key the server already
     * knows under this id are three different problems.
     *
     * A code rather than a message so the screen can say it in the reader's
     * language. The previous version returned English sentences, which appeared
     * verbatim in the middle of the Lao interface.
     */
    enum class ConnectionCode { CONNECTED, NOT_REGISTERED, KEY_CONFLICT, UNREACHABLE }

    /**
     * Ask the server two questions: are you there, and will you take my data.
     *
     * The second is answered by re-enrolling, which is idempotent — the server
     * returns the existing registration for a device whose key it already
     * holds, and refuses with 409 only if the key differs. That makes it a
     * genuine end-to-end check rather than a ping: it exercises TLS, the
     * hostname, the path, and the signature key in one go.
     */
    fun checkConnection(installId: String?, appVersion: String, hardwareBacked: Boolean): ConnectionStatus {
        val request = Request.Builder().url("$baseUrl/api/v1/health").get().build()

        try {
            http.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return ConnectionStatus(
                        ConnectionCode.UNREACHABLE,
                        "HTTP ${response.code}",
                    )
                }
            }
        } catch (error: Exception) {
            return ConnectionStatus(ConnectionCode.UNREACHABLE, error.message)
        }

        if (installId == null) return ConnectionStatus(ConnectionCode.NOT_REGISTERED)

        val enrolment = enroll(installId, appVersion, hardwareBacked)
        return when {
            enrolment.ok -> ConnectionStatus(ConnectionCode.CONNECTED)
            enrolment.error?.contains("409") == true ->
                ConnectionStatus(ConnectionCode.KEY_CONFLICT, enrolment.error)
            else -> ConnectionStatus(ConnectionCode.NOT_REGISTERED, enrolment.error)
        }
    }

    /**
     * Register this installation and its public key.
     *
     * A 409 means the id is already enrolled with a *different* key — the
     * server refuses to rotate, deliberately, so that knowing an install_id is
     * not enough to impersonate a device. The only recovery is a fresh id.
     */
    fun enroll(
        installId: String,
        appVersion: String,
        hardwareBacked: Boolean,
    ): EnrollResult {
        val body = JSONObject().apply {
            put("device", JSONObject().apply {
                put("install_id", installId)
                put("manufacturer", Build.MANUFACTURER)
                put("model", Build.MODEL)
                put("android_api", Build.VERSION.SDK_INT)
                put("app_version", appVersion)
            })
            put("public_key", DeviceKeystore.publicKeyBase64())
            put("key_algorithm", DeviceKeystore.KEY_ALGORITHM_NAME)
            put("hardware_backed", hardwareBacked)
        }

        val request = Request.Builder()
            .url("$baseUrl/api/v1/devices/enroll")
            .post(body.toString().toRequestBody(json))
            .build()

        return try {
            http.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (response.isSuccessful) {
                    EnrollResult(true, JSONObject(text).optString("trust_level"), null)
                } else {
                    EnrollResult(false, null, "HTTP ${response.code}: $text")
                }
            }
        } catch (error: Exception) {
            EnrollResult(false, null, error.message ?: "network error")
        }
    }

    /**
     * Per-record verdicts. The server answers 200 even when some records fail,
     * so a device on the edge of coverage never loses a whole batch to one bad
     * row — it may not get another upload window for days.
     */
    data class BatchResult(
        val ok: Boolean,
        val accepted: Int = 0,
        val duplicates: Int = 0,
        /** Ids the server refused. Every reason is permanent, so these are dropped too. */
        val rejectedIds: List<String> = emptyList(),
        val rejectionReasons: List<String> = emptyList(),
        val error: String? = null,
        /** True when retrying later could plausibly succeed. */
        val retryable: Boolean = true,
    )

    fun uploadBatch(
        installId: String,
        batchId: String,
        payloads: List<String>,
        uploadLat: Double?,
        uploadLon: Double?,
    ): BatchResult {
        val records = JSONArray()
        payloads.forEach { records.put(JSONObject(it)) }

        val body = JSONObject().apply {
            put("batch_id", batchId)
            put("device", JSONObject().apply { put("install_id", installId) })
            if (uploadLat != null && uploadLon != null) {
                put("uploaded_from_lat", uploadLat)
                put("uploaded_from_lon", uploadLon)
            }
            put("records", records)
        }

        val request = Request.Builder()
            .url("$baseUrl/api/v1/measurements/batch")
            .post(body.toString().toRequestBody(json))
            .build()

        return try {
            http.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()

                if (!response.isSuccessful) {
                    // 401 (not enrolled) and 403 (blocked) will not resolve by
                    // trying again; anything else might.
                    val retryable = response.code !in setOf(401, 403, 413)
                    return BatchResult(
                        ok = false,
                        error = "HTTP ${response.code}: $text",
                        retryable = retryable,
                    )
                }

                val parsed = JSONObject(text)
                val rejected = parsed.optJSONArray("rejected") ?: JSONArray()
                val ids = mutableListOf<String>()
                val reasons = mutableListOf<String>()
                for (i in 0 until rejected.length()) {
                    val entry = rejected.getJSONObject(i)
                    ids.add(entry.getString("client_record_id"))
                    reasons.add(entry.optString("reason"))
                }

                BatchResult(
                    ok = true,
                    accepted = parsed.optInt("accepted"),
                    duplicates = parsed.optInt("duplicates"),
                    rejectedIds = ids,
                    rejectionReasons = reasons,
                )
            }
        } catch (error: Exception) {
            BatchResult(ok = false, error = error.message ?: "network error", retryable = true)
        }
    }
}
