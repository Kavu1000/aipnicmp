package la.aipnicmp.collector

import la.aipnicmp.collector.collect.RadioSampler
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Operator codes must be well formed before they leave the phone.
 *
 * The server validates `mcc` against `^\d{3}$` and `mnc` against `^\d{2,3}$`,
 * and a record that fails is rejected whole — not stripped of its operator and
 * kept. The device then drops it and never sends it again. So a malformed PLMN
 * does not cost the attribution; it costs the measurement, and in a place
 * somebody drove to in order to measure it.
 *
 * Run with `./gradlew test`; no device needed.
 */
class RadioSamplerTest {

    @Test
    fun `splits a five digit plmn`() {
        val (mcc, mnc) = RadioSampler.plmnOf("45701")
        assertEquals("457", mcc)
        assertEquals("01", mnc)
    }

    @Test
    fun `splits a six digit plmn`() {
        val (mcc, mnc) = RadioSampler.plmnOf("457001")
        assertEquals("457", mcc)
        assertEquals("001", mnc)
    }

    @Test
    fun `refuses a plmn longer than six digits`() {
        // The bug this test exists for: substring(3) on a seven-character value
        // produced a four-digit MNC, which the server rejects — and with it the
        // whole record.
        val (mcc, mnc) = RadioSampler.plmnOf("4570123")
        assertNull(mcc)
        assertNull(mnc)
    }

    @Test
    fun `refuses a plmn that is not all digits`() {
        val (mcc, mnc) = RadioSampler.plmnOf("45.01")
        assertNull(mcc)
        assertNull(mnc)
    }

    @Test
    fun `refuses the empty string getNetworkOperator returns when unavailable`() {
        assertNull(RadioSampler.plmnOf("").first)
        assertNull(RadioSampler.plmnOf(null).first)
        assertNull(RadioSampler.plmnOf("457").first)
    }

    @Test
    fun `keeps well formed codes and drops malformed ones`() {
        assertEquals("457", RadioSampler.mccOf("457"))
        assertNull(RadioSampler.mccOf("45"))
        assertNull(RadioSampler.mccOf("4571"))
        assertNull(RadioSampler.mccOf("4a7"))

        assertEquals("01", RadioSampler.mncOf("01"))
        assertEquals("001", RadioSampler.mncOf("001"))
        assertNull(RadioSampler.mncOf("1"))
        assertNull(RadioSampler.mncOf("0123"))
    }
}
