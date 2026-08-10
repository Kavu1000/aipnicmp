package la.aipnicmp.collector.collect

import android.util.Log
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.roundToLong

/**
 * What the connection actually delivers, as opposed to what the bars claim.
 *
 * Signal strength is not speed. A phone can show four bars against a tower
 * whose backhaul is saturated, and a map built on RSRP alone would call that
 * village well served. Proposal 2.3 turns the points that carry both readings
 * into training labels for a model that estimates throughput everywhere else,
 * so these are the scarce, expensive samples the whole estimate rests on.
 *
 * Expensive literally: every run spends a collector's own mobile data. That
 * shapes everything here — the payload is small, the run is rare, and the
 * caller is expected to refuse far more often than it agrees.
 */
object SpeedTest {

    private const val TAG = "SpeedTest"

    /**
     * Bytes pulled per run. Small on purpose: 256 KB over a poor rural link is
     * already several seconds, and a larger sample would not change the verdict
     * for a map drawn in five colours.
     */
    const val PAYLOAD_BYTES = 262_144

    /** Round trips timed for latency. The best of three, not the mean — one
     *  scheduling hiccup on a busy handset should not become the finding. */
    private const val PING_ATTEMPTS = 3

    private const val CONNECT_TIMEOUT_MS = 10_000

    /**
     * Long enough for a genuinely slow link to finish, short enough that a
     * dying connection does not hold a foreground service open. A run that
     * times out reports nothing rather than a fabricated floor.
     */
    private const val READ_TIMEOUT_MS = 20_000

    data class Result(
        val downloadKbps: Double?,
        val latencyMs: Double?,
        /** Actually transferred, so the budget is charged what was spent. */
        val bytesUsed: Long,
    )

    fun run(baseUrl: String): Result {
        var spent = 0L
        val latency = measureLatency(baseUrl) { spent += it }
        val download = measureDownload(baseUrl) { spent += it }
        return Result(downloadKbps = download, latencyMs = latency, bytesUsed = spent)
    }

    private fun measureLatency(baseUrl: String, spend: (Long) -> Unit): Double? {
        var best: Double? = null
        repeat(PING_ATTEMPTS) {
            try {
                val connection = open("$baseUrl/api/v1/speedtest/ping")
                val started = System.nanoTime()
                connection.inputStream.use { it.readBytes() }
                val elapsed = (System.nanoTime() - started) / 1_000_000.0
                connection.disconnect()
                spend(64)
                if (best == null || elapsed < best!!) best = elapsed
            } catch (problem: Exception) {
                Log.w(TAG, "ping failed: ${problem.message}")
            }
        }
        return best
    }

    private fun measureDownload(baseUrl: String, spend: (Long) -> Unit): Double? {
        return try {
            val connection = open("$baseUrl/api/v1/speedtest/payload?bytes=$PAYLOAD_BYTES")
            // Timed from the first byte, not from connect: DNS, TCP and TLS are
            // real costs but they are latency, already measured above, and
            // counting them again here would depress the throughput figure on
            // exactly the weak links this project is looking for.
            connection.inputStream.use { stream ->
                val first = stream.read()
                if (first < 0) return null
                val started = System.nanoTime()
                val read = drain(stream) + 1
                val seconds = (System.nanoTime() - started) / 1_000_000_000.0
                connection.disconnect()
                spend(read.toLong())
                if (seconds <= 0.0 || read <= 0) null else (read * 8.0 / 1000.0) / seconds
            }
        } catch (problem: Exception) {
            Log.w(TAG, "download failed: ${problem.message}")
            null
        }
    }

    private fun drain(stream: InputStream): Int {
        val buffer = ByteArray(16 * 1024)
        var total = 0
        while (true) {
            val n = stream.read(buffer)
            if (n < 0) break
            total += n
        }
        return total
    }

    private fun open(url: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            useCaches = false
            // Compression would measure how fast the phone inflates zeros. The
            // server refuses it too; asking as well means a proxy in between
            // cannot quietly turn a rural link into a fast one.
            setRequestProperty("Accept-Encoding", "identity")
            setRequestProperty("Cache-Control", "no-store")
        }

    /** Rounded so a stored figure never implies more precision than a single
     *  256 KB sample over a moving handset can support. */
    fun round(value: Double?): Double? = value?.let { (it * 10).roundToLong() / 10.0 }
}
