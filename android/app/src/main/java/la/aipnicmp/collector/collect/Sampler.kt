package la.aipnicmp.collector.collect

import android.location.Location
import la.aipnicmp.collector.crypto.CanonicalMessage
import la.aipnicmp.collector.crypto.DeviceKeystore
import la.aipnicmp.collector.data.Measurement
import java.util.UUID

/**
 * Decides when to record, and turns a location plus a radio snapshot into a
 * signed measurement.
 *
 * Kept free of Android framework calls so the sampling rule can be unit-tested
 * without a device.
 */
class Sampler(
    /** Proposal 2.3: one record per 100 m… */
    private val minDistanceMetres: Double = 100.0,
    /** …or per 60 seconds, whichever comes first. */
    private val minIntervalMillis: Long = 60_000L,
) {

    private var lastLat: Double? = null
    private var lastLon: Double? = null
    private var lastMillis: Long = 0

    /**
     * Distance is checked as well as time so a stationary phone does not fill
     * the queue with identical readings, and time as well as distance so a slow
     * walk through a dead zone still produces evidence.
     */
    fun shouldSample(lat: Double, lon: Double, nowMillis: Long): Boolean {
        val previousLat = lastLat
        val previousLon = lastLon
        if (previousLat == null || previousLon == null) return true

        if (nowMillis - lastMillis >= minIntervalMillis) return true
        return haversineMetres(previousLat, previousLon, lat, lon) >= minDistanceMetres
    }

    fun markSampled(lat: Double, lon: Double, nowMillis: Long) {
        lastLat = lat
        lastLon = lon
        lastMillis = nowMillis
    }

    /**
     * Build and sign a record.
     *
     * Values are rounded *before* signing and the rounded values are what get
     * sent, so the server's own formatting of what it receives is a no-op and
     * the two sides cannot disagree about a half-way rounding case.
     */
    fun buildSigned(
        location: Location,
        radio: RadioSampler.RadioSnapshot,
        nowMillis: Long,
        speed: SpeedTest.Result? = null,
    ): Measurement {
        val lat = CanonicalMessage.roundCoordinate(location.latitude)
        val lon = CanonicalMessage.roundCoordinate(location.longitude)
        val rsrp = radio.rsrpDbm?.let { CanonicalMessage.roundRsrp(it) }

        val recordId = "and-" + UUID.randomUUID().toString().replace("-", "").take(20)
        val cellsVisible = (if (radio.servingCell != null) 1 else 0) + radio.neighbourCells.size

        val message = CanonicalMessage.build(
            clientRecordId = recordId,
            capturedAtMillis = nowMillis,
            lat = lat,
            lon = lon,
            registered = radio.registered,
            networkType = radio.networkType,
            rsrpDbm = rsrp,
            cellsVisible = cellsVisible,
        )

        return Measurement(
            clientRecordId = recordId,
            capturedAtMillis = nowMillis,
            lat = lat,
            lon = lon,
            gpsAccuracyM = location.accuracy.toDouble().takeIf { it > 0 },
            altitudeM = if (location.hasAltitude()) location.altitude else null,
            speedMps = if (location.hasSpeed()) location.speed.toDouble() else null,
            registered = radio.registered,
            networkType = radio.networkType,
            mcc = radio.mcc,
            mnc = radio.mnc,
            operatorName = radio.operatorName,
            rsrpDbm = rsrp,
            rsrqDb = radio.rsrqDb,
            sinrDb = radio.sinrDb,
            rssiDbm = radio.rssiDbm,
            level = radio.level,
            servingCell = radio.servingCell,
            neighbourCells = radio.neighbourCells,
            // Outside the signed message on purpose. The signature covers what
            // the radio reported; throughput is measured afterwards, by this
            // app rather than by the modem, and folding it in would mean
            // changing the canonical string on both sides for a field the
            // server does not need to trust the same way.
            downloadKbps = SpeedTest.round(speed?.downloadKbps),
            latencyMs = SpeedTest.round(speed?.latencyMs),
            signature = DeviceKeystore.sign(message),
        )
    }

    companion object {
        private const val EARTH_RADIUS_M = 6_371_008.8

        fun haversineMetres(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
            val phi1 = Math.toRadians(lat1)
            val phi2 = Math.toRadians(lat2)
            val deltaPhi = phi2 - phi1
            val deltaLambda = Math.toRadians(lon2 - lon1)
            val a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
                Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2)
            return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a))
        }
    }
}
