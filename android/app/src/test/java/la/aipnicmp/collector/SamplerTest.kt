package la.aipnicmp.collector

import la.aipnicmp.collector.collect.Sampler
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The sampling rule of proposal 2.3: a record every 100 m, or every 60
 * seconds, whichever comes first.
 *
 * The time branch is the one that matters most and the one that was silently
 * disabled: the location request carried a 50 m displacement filter, so a
 * stationary phone received no fixes at all and this class was never asked.
 * A collector parked in a village with no service recorded nothing for as long
 * as they stayed there — no evidence produced by exactly the situation the
 * project exists to document.
 */
class SamplerTest {

    private val start = 1_000_000L

    @Test
    fun `the first reading is always taken`() {
        assertTrue(Sampler().shouldSample(17.9757, 102.6331, start))
    }

    @Test
    fun `a stationary phone still records once a minute`() {
        val sampler = Sampler()
        sampler.markSampled(17.9757, 102.6331, start)

        // Same spot, half a minute later: nothing new to say yet.
        assertFalse(sampler.shouldSample(17.9757, 102.6331, start + 30_000L))

        // Same spot, a minute later: a dead zone endured is a finding.
        assertTrue(sampler.shouldSample(17.9757, 102.6331, start + 60_000L))
    }

    @Test
    fun `moving 100 m records without waiting for the minute`() {
        val sampler = Sampler()
        sampler.markSampled(17.9757, 102.6331, start)

        // Roughly 111 m north, one second later.
        assertTrue(sampler.shouldSample(17.9767, 102.6331, start + 1_000L))
    }

    @Test
    fun `a small shuffle does not fill the queue`() {
        val sampler = Sampler()
        sampler.markSampled(17.9757, 102.6331, start)

        // About 11 m — GPS jitter while parked, not a new place.
        assertFalse(sampler.shouldSample(17.9758, 102.6331, start + 5_000L))
    }
}
