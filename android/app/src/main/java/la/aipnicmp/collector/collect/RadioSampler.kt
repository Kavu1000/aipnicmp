package la.aipnicmp.collector.collect

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.CellInfo
import android.telephony.CellInfoGsm
import android.telephony.CellInfoLte
import android.telephony.CellInfoNr
import android.telephony.CellInfoWcdma
import android.telephony.CellSignalStrengthLte
import android.telephony.CellSignalStrengthNr
import android.telephony.TelephonyManager
import androidx.core.content.ContextCompat
import la.aipnicmp.collector.data.CellObservation

/**
 * Reads the radio.
 *
 * The premise of the whole project lives here: the modem scans for base
 * stations whether or not any data is flowing, so a phone with no usable
 * internet can still report exactly what it can see. A place where
 * [readCells] comes back empty is not a failed reading — it is the most
 * valuable reading the system collects, because it says no tower reaches here.
 */
class RadioSampler(private val context: Context) {

    private val telephony: TelephonyManager? =
        ContextCompat.getSystemService(context, TelephonyManager::class.java)

    /** Android returns this for "unknown", and it must never be sent as a value. */
    private val UNAVAILABLE = Int.MAX_VALUE

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    data class RadioSnapshot(
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
    )

    @SuppressLint("MissingPermission")
    fun sample(): RadioSnapshot {
        val manager = telephony
        if (manager == null || !hasPermission()) {
            return RadioSnapshot(
                registered = false, networkType = null, mcc = null, mnc = null,
                operatorName = null, rsrpDbm = null, rsrqDb = null, sinrDb = null,
                rssiDbm = null, level = null, servingCell = null, neighbourCells = emptyList(),
            )
        }

        val cells: List<CellInfo> = try {
            manager.allCellInfo ?: emptyList()
        } catch (_: SecurityException) {
            emptyList()
        }

        val observations = cells.mapNotNull { toObservation(it) }
        val serving = observations.firstOrNull { it.isRegistered }
        val neighbours = observations.filterNot { it.isRegistered }

        // "Registered" means the modem is actually attached, not merely that it
        // can see something. The distinction separates "a tower exists but the
        // phone cannot use it" from "the phone is connected" — two states with
        // very different costs to fix.
        val registered = cells.any { it.isRegistered } && hasServiceState(manager)

        val lte = cells.filterIsInstance<CellInfoLte>().firstOrNull { it.isRegistered }
        val nr = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            cells.filterIsInstance<CellInfoNr>().firstOrNull { it.isRegistered }
        } else {
            null
        }

        var rsrp: Double? = null
        var rsrq: Double? = null
        var sinr: Double? = null
        var rssi: Double? = null
        var level: Int? = null

        if (lte != null) {
            val strength = lte.cellSignalStrength as CellSignalStrengthLte
            rsrp = strength.rsrp.takeIf { it != UNAVAILABLE }?.toDouble()
            rsrq = strength.rsrq.takeIf { it != UNAVAILABLE }?.toDouble()
            sinr = strength.rssnr.takeIf { it != UNAVAILABLE }?.toDouble()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                rssi = strength.rssi.takeIf { it != UNAVAILABLE }?.toDouble()
            }
            level = strength.level
        } else if (nr != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val strength = nr.cellSignalStrength as CellSignalStrengthNr
            rsrp = strength.ssRsrp.takeIf { it != UNAVAILABLE }?.toDouble()
            rsrq = strength.ssRsrq.takeIf { it != UNAVAILABLE }?.toDouble()
            sinr = strength.ssSinr.takeIf { it != UNAVAILABLE }?.toDouble()
            level = strength.level
        } else if (serving != null) {
            level = cells.firstOrNull { it.isRegistered }?.cellSignalStrength?.level
        }

        val networkType = when {
            !registered -> null
            nr != null -> "NR"
            lte != null -> "LTE"
            cells.any { it.isRegistered && it is CellInfoWcdma } -> "UMTS"
            cells.any { it.isRegistered && it is CellInfoGsm } -> "GSM"
            else -> null
        }

        return RadioSnapshot(
            registered = registered,
            networkType = networkType,
            mcc = serving?.mcc ?: manager.networkOperator.takeIf { it.length >= 5 }?.substring(0, 3),
            mnc = serving?.mnc ?: manager.networkOperator.takeIf { it.length >= 5 }?.substring(3),
            operatorName = manager.networkOperatorName?.takeIf { it.isNotBlank() },
            rsrpDbm = rsrp,
            rsrqDb = rsrq,
            sinrDb = sinr,
            rssiDbm = rssi,
            level = level,
            servingCell = serving,
            // The server accepts at most 32; more than that is noise anyway.
            neighbourCells = neighbours.take(31),
        )
    }

    @SuppressLint("MissingPermission")
    private fun hasServiceState(manager: TelephonyManager): Boolean = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.serviceState?.state == android.telephony.ServiceState.STATE_IN_SERVICE
        } else {
            true
        }
    } catch (_: SecurityException) {
        // Without the reading, fall back to what the cell list already implies.
        true
    }

    private fun toObservation(info: CellInfo): CellObservation? = when (info) {
        is CellInfoLte -> {
            val identity = info.cellIdentity
            val strength = info.cellSignalStrength as CellSignalStrengthLte
            CellObservation(
                radio = "LTE",
                mcc = mccOf(identity.mccString),
                mnc = mncOf(identity.mncString),
                cid = identity.ci.takeIf { it != UNAVAILABLE }?.toLong(),
                lacTac = identity.tac.takeIf { it != UNAVAILABLE },
                pciPsc = identity.pci.takeIf { it != UNAVAILABLE },
                arfcn = identity.earfcn.takeIf { it != UNAVAILABLE },
                rsrpDbm = strength.rsrp.takeIf { it != UNAVAILABLE }?.toDouble(),
                isRegistered = info.isRegistered,
            )
        }

        is CellInfoWcdma -> {
            val identity = info.cellIdentity
            CellObservation(
                radio = "UMTS",
                mcc = mccOf(identity.mccString),
                mnc = mncOf(identity.mncString),
                cid = identity.cid.takeIf { it != UNAVAILABLE }?.toLong(),
                lacTac = identity.lac.takeIf { it != UNAVAILABLE },
                pciPsc = identity.psc.takeIf { it != UNAVAILABLE },
                arfcn = identity.uarfcn.takeIf { it != UNAVAILABLE },
                rsrpDbm = null,
                isRegistered = info.isRegistered,
            )
        }

        is CellInfoGsm -> {
            val identity = info.cellIdentity
            CellObservation(
                radio = "GSM",
                mcc = mccOf(identity.mccString),
                mnc = mncOf(identity.mncString),
                cid = identity.cid.takeIf { it != UNAVAILABLE }?.toLong(),
                lacTac = identity.lac.takeIf { it != UNAVAILABLE },
                pciPsc = null,
                arfcn = identity.arfcn.takeIf { it != UNAVAILABLE },
                rsrpDbm = null,
                isRegistered = info.isRegistered,
            )
        }

        else -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && info is CellInfoNr) {
            val identity = info.cellIdentity as? android.telephony.CellIdentityNr
            val strength = info.cellSignalStrength as CellSignalStrengthNr
            CellObservation(
                radio = "NR",
                mcc = mccOf(identity?.mccString),
                mnc = mncOf(identity?.mncString),
                cid = identity?.nci?.takeIf { it != Long.MAX_VALUE },
                lacTac = identity?.tac?.takeIf { it != UNAVAILABLE },
                pciPsc = identity?.pci?.takeIf { it != UNAVAILABLE },
                arfcn = identity?.nrarfcn?.takeIf { it != UNAVAILABLE },
                rsrpDbm = strength.ssRsrp.takeIf { it != UNAVAILABLE }?.toDouble(),
                isRegistered = info.isRegistered,
            )
        } else {
            null
        }
    }

    // The server validates these against ^\d{3}$ and ^\d{2,3}$, so anything
    // malformed is dropped here rather than costing the record its upload.
    private fun mccOf(value: String?): String? = value?.takeIf { it.length == 3 && it.all(Char::isDigit) }

    private fun mncOf(value: String?): String? =
        value?.takeIf { it.length in 2..3 && it.all(Char::isDigit) }
}
