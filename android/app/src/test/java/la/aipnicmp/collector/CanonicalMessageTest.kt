package la.aipnicmp.collector

import la.aipnicmp.collector.crypto.CanonicalMessage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.util.Locale

/**
 * The canonical message must match the server byte for byte.
 *
 * These expectations mirror `backend/tests/test_signing.py`. If the two files
 * ever disagree, every record this app produces will be rejected as
 * `bad_signature` — with no other symptom, because the record itself will look
 * perfectly well-formed. Run with `./gradlew test`; no device needed.
 */
class CanonicalMessageTest {

    private val capturedAt = Instant.parse("2026-08-08T04:31:07Z").toEpochMilli()

    @Test
    fun `builds the exact string the server verifies`() {
        val message = CanonicalMessage.build(
            clientRecordId = "rec-abc12345",
            capturedAtMillis = capturedAt,
            lat = 19.8845,
            lon = 102.135,
            registered = true,
            networkType = "LTE",
            rsrpDbm = -95.0,
            cellsVisible = 3,
        ).toString(Charsets.UTF_8)

        assertEquals(
            "v1|rec-abc12345|2026-08-08T04:31:07Z|19.884500|102.135000|1|LTE|-95.0|3",
            message,
        )
    }

    @Test
    fun `a missing rsrp is an empty field, never a zero`() {
        // A zero would read as -0 dBm: a physically impossible signal, and one
        // the server would reject as implausible.
        val message = CanonicalMessage.build(
            clientRecordId = "rec-nosignal01",
            capturedAtMillis = capturedAt,
            lat = 19.8845,
            lon = 102.135,
            registered = false,
            networkType = null,
            rsrpDbm = null,
            cellsVisible = 0,
        ).toString(Charsets.UTF_8)

        assertEquals(
            "v1|rec-nosignal01|2026-08-08T04:31:07Z|19.884500|102.135000|0|||0",
            message,
        )
    }

    @Test
    fun `formatting ignores the phone's locale`() {
        // A phone set to Lao or French renders 19.8845 as "19,884500" under the
        // default locale, and every signature silently fails to verify. This is
        // the single most likely way for this app to break in the field.
        val original = Locale.getDefault()
        try {
            Locale.setDefault(Locale.forLanguageTag("fr-FR"))
            val message = CanonicalMessage.build(
                clientRecordId = "rec-locale0001",
                capturedAtMillis = capturedAt,
                lat = 19.8845,
                lon = 102.135,
                registered = true,
                networkType = "LTE",
                rsrpDbm = -95.5,
                cellsVisible = 2,
            ).toString(Charsets.UTF_8)

            assertTrue("comma decimal separator leaked in: $message", !message.contains(","))
            assertTrue(message.contains("19.884500"))
            assertTrue(message.contains("-95.5"))
        } finally {
            Locale.setDefault(original)
        }
    }

    @Test
    fun `timestamps are truncated to whole seconds in UTC`() {
        val withMillis = capturedAt + 837
        assertEquals("2026-08-08T04:31:07Z", CanonicalMessage.formatTimestamp(withMillis))
    }

    @Test
    fun `coordinates are rounded before signing, not after`() {
        // The rounded value is what gets signed *and* what gets sent, so the
        // server re-formatting it is a no-op and neither side can disagree
        // about a half-way case.
        val rounded = CanonicalMessage.roundCoordinate(19.88451234)
        assertEquals("19.884512", CanonicalMessage.formatCoordinate(rounded))
        assertEquals(rounded, CanonicalMessage.roundCoordinate(rounded), 0.0)
    }

    @Test
    fun `network type is upper-cased`() {
        val message = CanonicalMessage.build(
            clientRecordId = "rec-lowercase1",
            capturedAtMillis = capturedAt,
            lat = 19.0,
            lon = 102.0,
            registered = true,
            networkType = "lte",
            rsrpDbm = -100.0,
            cellsVisible = 1,
        ).toString(Charsets.UTF_8)

        assertTrue(message.contains("|LTE|"))
    }
}
