package la.aipnicmp.collector.data

import org.json.JSONObject

/**
 * One record, flattened for display.
 *
 * Parsed back out of the stored payload rather than kept as separate columns.
 * The payload is the thing that was signed and must never be rebuilt, so it is
 * the single source of truth for what this record actually says — reading it
 * back cannot drift from what will be uploaded.
 */
data class RecordSummary(
    val clientRecordId: String,
    val capturedAtMillis: Long,
    val lat: Double,
    val lon: Double,
    val accuracyM: Double?,
    val registered: Boolean,
    val networkType: String?,
    val operator: String?,
    val rsrpDbm: Double?,
    val cellsVisible: Int,
    val state: RadioState,
    /** null while queued; otherwise what the server said. */
    val outcome: String? = null,
    val sentAtMillis: Long? = null,
) {
    companion object {
        fun fromPayload(
            payload: String,
            capturedAtMillis: Long,
            outcome: String? = null,
            sentAtMillis: Long? = null,
        ): RecordSummary? = try {
            val json = JSONObject(payload)
            val signal = json.optJSONObject("signal")
            val serving = json.optJSONObject("serving_cell")
            val neighbours = json.optJSONArray("neighbor_cells")

            val cells = (if (serving != null) 1 else 0) + (neighbours?.length() ?: 0)
            val rsrp = signal?.takeIf { it.has("rsrp_dbm") }?.optDouble("rsrp_dbm")
                ?.takeIf { !it.isNaN() }
            val sinr = signal?.takeIf { it.has("sinr_db") }?.optDouble("sinr_db")
                ?.takeIf { !it.isNaN() }
            val registered = json.optBoolean("registered", false)
            val network = json.optString("network_type").takeIf { it.isNotBlank() && it != "null" }

            RecordSummary(
                clientRecordId = json.optString("client_record_id"),
                capturedAtMillis = capturedAtMillis,
                lat = json.optDouble("lat"),
                lon = json.optDouble("lon"),
                accuracyM = json.takeIf { it.has("gps_accuracy_m") }?.optDouble("gps_accuracy_m")
                    ?.takeIf { !it.isNaN() },
                registered = registered,
                networkType = network,
                operator = json.optJSONObject("operator")?.optString("name")
                    ?.takeIf { it.isNotBlank() && it != "null" },
                rsrpDbm = rsrp,
                cellsVisible = cells,
                state = RadioStates.classify(registered, network, cells, rsrp, sinr),
                outcome = outcome,
                sentAtMillis = sentAtMillis,
            )
        } catch (_: Exception) {
            // A record that cannot be parsed is still uploadable — the payload
            // is untouched. It simply cannot be shown, which must not crash the
            // list or hide everything else in it.
            null
        }
    }
}
