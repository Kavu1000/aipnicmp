package la.aipnicmp.collector.crypto

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Builds the exact bytes the server verifies against.
 *
 * The counterpart is `backend/app/services/signing.py::canonical_message`, and
 * `backend/tests/test_signing.py` pins the field layout. Any divergence means
 * every record this device produces is rejected as `bad_signature`, so the two
 * implementations must be changed together.
 *
 * Two traps are handled deliberately here:
 *
 *  - **Locale.** A phone set to Lao or French formats 19.8845 as "19,884500",
 *    and every signature silently fails. Every format call pins [Locale.ROOT].
 *  - **Rounding drift.** Values are rounded *before* signing, and the same
 *    rounded values are what get sent. The server re-formats what it receives,
 *    so its formatting is a no-op and the two sides cannot disagree about a
 *    half-way case.
 */
object CanonicalMessage {

    const val VERSION = "v1"

    /** Coordinates: 6 decimal places is ~0.1 m, finer than any phone's GPS. */
    const val COORD_DECIMALS = 6

    /** Signal strength: 1 decimal place. Android reports whole dBm anyway. */
    const val RSRP_DECIMALS = 1

    private val timestampFormat: SimpleDateFormat
        get() = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.ROOT).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }

    /**
     * UTC, whole seconds, `Z` suffix — e.g. `2026-08-08T04:31:07Z`.
     *
     * Truncated rather than rounded, so the timestamp that is signed is always
     * the timestamp that is sent.
     */
    fun formatTimestamp(epochMillis: Long): String =
        timestampFormat.format(Date(epochMillis / 1000L * 1000L))

    /** Round to the precision that will be both signed and transmitted. */
    fun roundCoordinate(value: Double): Double = round(value, COORD_DECIMALS)

    fun roundRsrp(value: Double): Double = round(value, RSRP_DECIMALS)

    private fun round(value: Double, decimals: Int): Double {
        var factor = 1.0
        repeat(decimals) { factor *= 10.0 }
        return Math.round(value * factor) / factor
    }

    fun formatCoordinate(value: Double): String =
        String.format(Locale.ROOT, "%.${COORD_DECIMALS}f", value)

    fun formatRsrp(value: Double?): String =
        if (value == null) "" else String.format(Locale.ROOT, "%.${RSRP_DECIMALS}f", value)

    /**
     * `v1|<id>|<captured_at>|<lat>|<lon>|<registered>|<network>|<rsrp>|<cells>`
     *
     * Only the fields a forger would want to change are covered. Adding one
     * means a `v2` version string on both sides.
     */
    fun build(
        clientRecordId: String,
        capturedAtMillis: Long,
        lat: Double,
        lon: Double,
        registered: Boolean,
        networkType: String?,
        rsrpDbm: Double?,
        cellsVisible: Int,
    ): ByteArray {
        val fields = listOf(
            VERSION,
            clientRecordId,
            formatTimestamp(capturedAtMillis),
            formatCoordinate(lat),
            formatCoordinate(lon),
            if (registered) "1" else "0",
            networkType?.uppercase(Locale.ROOT).orEmpty(),
            formatRsrp(rsrpDbm),
            cellsVisible.toString(),
        )
        return fields.joinToString("|").toByteArray(Charsets.UTF_8)
    }
}
