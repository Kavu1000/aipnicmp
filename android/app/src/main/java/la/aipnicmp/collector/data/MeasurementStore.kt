package la.aipnicmp.collector.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject

/**
 * The store-and-forward queue.
 *
 * This is the heart of proposal 2.3. A reading taken where there is no network
 * is written here, signed, and waits — for minutes or for a fortnight — until
 * the phone reaches coverage again. Those are the records the map cannot get
 * any other way, so losing one is worse than losing a reading from a town.
 *
 * Records are stored as the finished JSON payload rather than as columns. The
 * row is written once, immediately after signing, and is never edited again:
 * re-serialising it later could produce different bytes from the ones that were
 * signed, and the signature would fail for a record that was never tampered
 * with.
 *
 * Plain SQLite rather than Room, deliberately — no annotation processor means
 * one less thing that can break a build nobody can compile-check remotely.
 */
class MeasurementStore(context: Context) :
    SQLiteOpenHelper(context.applicationContext, DATABASE_NAME, null, VERSION) {

    companion object {
        private const val DATABASE_NAME = "collector.db"
        private const val VERSION = 1
        private const val TABLE = "queued_measurements"

        /**
         * Queue cap from proposal 2.3, so a phone that never regains coverage
         * cannot fill its own storage. At roughly 1 KB per record this is a few
         * tens of megabytes — weeks of continuous collection.
         */
        const val MAX_QUEUED_RECORDS = 20_000
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE $TABLE (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_record_id TEXT NOT NULL UNIQUE,
                captured_at_millis INTEGER NOT NULL,
                payload TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX idx_captured_at ON $TABLE (captured_at_millis)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // No migrations yet. When one is needed, migrate rather than drop:
        // queued records may be the only evidence that a place has no coverage.
    }

    fun enqueue(record: Measurement, payload: JSONObject): Boolean {
        val values = ContentValues().apply {
            put("client_record_id", record.clientRecordId)
            put("captured_at_millis", record.capturedAtMillis)
            put("payload", payload.toString())
        }
        // CONFLICT_IGNORE keeps a duplicate id from throwing; the record is
        // already queued, which is exactly the desired end state.
        val id = writableDatabase.insertWithOnConflict(
            TABLE, null, values, SQLiteDatabase.CONFLICT_IGNORE
        )
        if (id != -1L) trimIfOversized()
        return id != -1L
    }

    /**
     * Oldest first: a record's value does not decay, but the server rejects
     * anything older than 30 days, so the oldest are the ones at risk.
     */
    fun peekBatch(limit: Int): List<QueuedRecord> {
        val out = mutableListOf<QueuedRecord>()
        readableDatabase.query(
            TABLE,
            arrayOf("id", "client_record_id", "payload"),
            null, null, null, null,
            "captured_at_millis ASC",
            limit.toString(),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                out.add(
                    QueuedRecord(
                        id = cursor.getLong(0),
                        clientRecordId = cursor.getString(1),
                        payload = cursor.getString(2),
                    )
                )
            }
        }
        return out
    }

    /** Called for accepted, duplicate *and* rejected ids: every server verdict is final. */
    fun delete(ids: List<Long>) {
        if (ids.isEmpty()) return
        val placeholders = ids.joinToString(",") { "?" }
        writableDatabase.delete(
            TABLE, "id IN ($placeholders)", ids.map { it.toString() }.toTypedArray()
        )
    }

    fun markAttempted(ids: List<Long>) {
        if (ids.isEmpty()) return
        val placeholders = ids.joinToString(",") { "?" }
        writableDatabase.execSQL(
            "UPDATE $TABLE SET attempts = attempts + 1 WHERE id IN ($placeholders)",
            ids.map { it.toString() }.toTypedArray(),
        )
    }

    fun count(): Int = readableDatabase.rawQuery("SELECT COUNT(*) FROM $TABLE", null).use {
        if (it.moveToFirst()) it.getInt(0) else 0
    }

    fun oldestCapturedAt(): Long? =
        readableDatabase.rawQuery("SELECT MIN(captured_at_millis) FROM $TABLE", null).use {
            if (it.moveToFirst() && !it.isNull(0)) it.getLong(0) else null
        }

    /**
     * Drops the *newest* records when the cap is hit, not the oldest.
     *
     * Counter-intuitive, and deliberate: the oldest queued records are the ones
     * closest to the server's 30-day cutoff, so discarding them would waste the
     * evidence that has already waited longest. A phone this far behind is in a
     * long dead zone, which is the case worth protecting.
     */
    private fun trimIfOversized() {
        val excess = count() - MAX_QUEUED_RECORDS
        if (excess <= 0) return
        writableDatabase.execSQL(
            """
            DELETE FROM $TABLE WHERE id IN (
                SELECT id FROM $TABLE ORDER BY captured_at_millis DESC LIMIT ?
            )
            """.trimIndent(),
            arrayOf(excess.toString()),
        )
    }
}

data class QueuedRecord(val id: Long, val clientRecordId: String, val payload: String)
