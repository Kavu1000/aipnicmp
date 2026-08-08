package la.aipnicmp.collector.data

import org.json.JSONArray
import org.json.JSONObject

/** One cell as the modem reported it. */
data class CellObservation(
    val radio: String?,
    val mcc: String?,
    val mnc: String?,
    val cid: Long?,
    val lacTac: Int?,
    val pciPsc: Int?,
    val arfcn: Int?,
    val rsrpDbm: Double?,
    val isRegistered: Boolean,
) {
    fun toJson(): JSONObject = JSONObject().apply {
        putOrNull("radio", radio)
        putOrNull("mcc", mcc)
        putOrNull("mnc", mnc)
        putOrNull("cid", cid)
        putOrNull("lac_tac", lacTac)
        putOrNull("pci_psc", pciPsc)
        putOrNull("arfcn", arfcn)
        putOrNull("rsrp_dbm", rsrpDbm)
        put("is_registered", isRegistered)
    }
}

/**
 * One reading, already rounded to the precision that will be signed.
 *
 * Nothing here identifies a person. That is not an oversight to be corrected
 * later — proposal 2.6 promises anonymised data, and the cheapest way to keep
 * that promise is never to collect the identifying field at all.
 */
data class Measurement(
    val clientRecordId: String,
    val capturedAtMillis: Long,
    val lat: Double,
    val lon: Double,
    val gpsAccuracyM: Double?,
    val altitudeM: Double?,
    val speedMps: Double?,
    val registered: Boolean,
    val networkType: String?,
    val mcc: String?,
    val mnc: String?,
    val operatorName: String?,
    val rsrpDbm: Double?,
    val rsrqDb: Double?,
    val sinrDb: Double?,
    val rssiDbm: Double?,
    val level: Int?,
    val servingCell: CellObservation?,
    val neighbourCells: List<CellObservation>,
    val downloadKbps: Double? = null,
    val uploadKbps: Double? = null,
    val latencyMs: Double? = null,
    val signature: String? = null,
) {
    val cellsVisible: Int
        get() = (if (servingCell != null) 1 else 0) + neighbourCells.size

    fun toJson(timestamp: String): JSONObject = JSONObject().apply {
        put("client_record_id", clientRecordId)
        put("captured_at", timestamp)
        put("lat", lat)
        put("lon", lon)
        putOrNull("gps_accuracy_m", gpsAccuracyM)
        putOrNull("altitude_m", altitudeM)
        putOrNull("speed_mps", speedMps)
        put("registered", registered)
        putOrNull("network_type", networkType)

        if (mcc != null || mnc != null || operatorName != null) {
            put("operator", JSONObject().apply {
                putOrNull("mcc", mcc)
                putOrNull("mnc", mnc)
                putOrNull("name", operatorName)
            })
        }

        put("signal", JSONObject().apply {
            putOrNull("rsrp_dbm", rsrpDbm)
            putOrNull("rsrq_db", rsrqDb)
            putOrNull("sinr_db", sinrDb)
            putOrNull("rssi_dbm", rssiDbm)
            putOrNull("level", level)
        })

        if (servingCell != null) put("serving_cell", servingCell.toJson())
        if (neighbourCells.isNotEmpty()) {
            put("neighbor_cells", JSONArray().apply {
                neighbourCells.forEach { put(it.toJson()) }
            })
        }

        // An active test is only ever present when the device was registered;
        // the server rejects the combination outright, because a speed test
        // without a data connection cannot have happened.
        if (downloadKbps != null || latencyMs != null) {
            put("active_test", JSONObject().apply {
                putOrNull("download_kbps", downloadKbps)
                putOrNull("upload_kbps", uploadKbps)
                putOrNull("latency_ms", latencyMs)
            })
        }

        putOrNull("signature", signature)
    }
}

/**
 * `JSONObject.put` stores the string "null" for a null value, which the server
 * would then reject as a malformed field. Omitting the key is what "the device
 * did not report this" means on the wire.
 */
internal fun JSONObject.putOrNull(key: String, value: Any?) {
    if (value != null) put(key, value)
}
