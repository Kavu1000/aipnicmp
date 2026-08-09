package la.aipnicmp.collector.data

/**
 * The five states of proposal 2.3, mirrored on the device.
 *
 * The server derives its own value and that one is authoritative — thresholds
 * will be retuned as real Lao data arrives, and a phone in the field cannot be
 * updated to match. This copy exists for two narrower purposes: labelling the
 * records list so a collector can see what they are gathering, and filling
 * `radio_state_client`, which the server stores beside its own answer precisely
 * so the two can be compared and any drift noticed.
 *
 * If these thresholds and the server's disagree, the server wins. That is the
 * design, not an accident.
 */
enum class RadioState {
    NO_CELL,
    CELLS_VISIBLE_UNREGISTERED,
    REGISTERED_2G_3G,
    LTE_WEAK,
    LTE_GOOD,
}

object RadioStates {

    /** Proposal 2.3: below this, data works but is slow. */
    private const val RSRP_GOOD_DBM = -110.0
    private const val SINR_GOOD_DB = 0.0

    private val BROADBAND = setOf("LTE", "LTE_CA", "NR", "NR_NSA", "IWLAN")

    fun classify(
        registered: Boolean,
        networkType: String?,
        cellsVisible: Int,
        rsrpDbm: Double?,
        sinrDb: Double? = null,
    ): RadioState {
        if (cellsVisible <= 0) return RadioState.NO_CELL
        if (!registered) return RadioState.CELLS_VISIBLE_UNREGISTERED

        val normalised = networkType?.uppercase()?.replace("-", "_")
        if (normalised !in BROADBAND) return RadioState.REGISTERED_2G_3G

        if (rsrpDbm != null) {
            return if (rsrpDbm >= RSRP_GOOD_DBM) RadioState.LTE_GOOD else RadioState.LTE_WEAK
        }
        if (sinrDb != null) {
            return if (sinrDb >= SINR_GOOD_DB) RadioState.LTE_GOOD else RadioState.LTE_WEAK
        }
        // Registered on LTE but no usable metric. Assume the pessimistic side:
        // overstating coverage is the failure that costs a village its tower.
        return RadioState.LTE_WEAK
    }
}
