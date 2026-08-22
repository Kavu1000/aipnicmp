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
        private const val VERSION = 3
        private const val TABLE = "queued_measurements"
        private const val SENT_TABLE = "sent_measurements"

        /**
         * How many uploaded records to remember for the history view. Enough
         * to review a day's collecting; small enough that it can never rival
         * the queue itself for space, which is what the storage cap protects.
         */
        const val SENT_HISTORY_LIMIT = 300

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
                attempts INTEGER NOT NULL DEFAULT 0,
                was_offline INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX idx_captured_at ON $TABLE (captured_at_millis)")
        createSentTable(db)
    }

    /**
     * A short history of what was uploaded and what the server said about it.
     *
     * The queue deletes a record the moment the server rules on it, which is
     * correct — but it left the collector with nothing but a counter. Someone
     * who has just driven a mountain road deserves to see what they actually
     * gathered, and to see plainly if the server refused it and why.
     */
    private fun createSentTable(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS $SENT_TABLE (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_record_id TEXT NOT NULL,
                captured_at_millis INTEGER NOT NULL,
                sent_at_millis INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                payload TEXT NOT NULL,
                was_offline INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_sent_at ON $SENT_TABLE (sent_at_millis)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // Migrate, never drop: queued records may be the only evidence that a
        // place has no coverage, and they cannot be collected again.
        if (oldVersion < 2) createSentTable(db)
        if (oldVersion < 3) {
            // Records captured before this column existed are marked as taken
            // online, which is the safe assumption: the app could only have
            // uploaded them at all if it had a network at some point.
            db.execSQL("ALTER TABLE $TABLE ADD COLUMN was_offline INTEGER NOT NULL DEFAULT 0")
            db.execSQL("ALTER TABLE $SENT_TABLE ADD COLUMN was_offline INTEGER NOT NULL DEFAULT 0")
        }
    }

    /**
     * @param wasOffline whether the phone had no usable internet at capture.
     *   Stored beside the record rather than inside the payload: the payload is
     *   the signed wire format and the server rejects unknown fields outright.
     *   This is local context for the collector, not evidence about the place.
     */
    fun enqueue(record: Measurement, payload: JSONObject, wasOffline: Boolean): Boolean {
        val values = ContentValues().apply {
            put("client_record_id", record.clientRecordId)
            put("captured_at_millis", record.capturedAtMillis)
            put("payload", payload.toString())
            put("was_offline", if (wasOffline) 1 else 0)
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
            arrayOf("id", "client_record_id", "payload", "captured_at_millis", "was_offline"),
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
                        capturedAtMillis = cursor.getLong(3),
                        wasOffline = cursor.getInt(4) == 1,
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

    /** Queued records, oldest first — the order they will be uploaded in. */
    fun listPending(limit: Int = 200): List<RecordSummary> {
        val out = mutableListOf<RecordSummary>()
        readableDatabase.query(
            TABLE,
            arrayOf("captured_at_millis", "payload", "was_offline"),
            null, null, null, null,
            "captured_at_millis ASC",
            limit.toString(),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                RecordSummary.fromPayload(
                    payload = cursor.getString(1),
                    capturedAtMillis = cursor.getLong(0),
                    wasOffline = cursor.getInt(2) == 1,
                )?.let(out::add)
            }
        }
        return out
    }

    /** Uploaded records, most recent first. */
    fun listSent(limit: Int = 200): List<RecordSummary> {
        val out = mutableListOf<RecordSummary>()
        readableDatabase.query(
            SENT_TABLE,
            arrayOf("captured_at_millis", "payload", "outcome", "sent_at_millis", "was_offline"),
            null, null, null, null,
            "sent_at_millis DESC, id DESC",
            limit.toString(),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                RecordSummary.fromPayload(
                    payload = cursor.getString(1),
                    capturedAtMillis = cursor.getLong(0),
                    outcome = cursor.getString(2),
                    sentAtMillis = cursor.getLong(3),
                    wasOffline = cursor.getInt(4) == 1,
                )?.let(out::add)
            }
        }
        return out
    }

    fun sentCount(): Int = readableDatabase.rawQuery("SELECT COUNT(*) FROM $SENT_TABLE", null).use {
        if (it.moveToFirst()) it.getInt(0) else 0
    }

    /**
     * Remember what the server said before the queued rows are deleted.
     *
     * Recorded for rejections too, and with the reason: a collector whose
     * records are all being refused should be able to see that from the phone
     * rather than discovering it weeks later from an empty map.
     */
    fun recordSent(records: List<QueuedRecord>, outcomes: Map<String, String>) {
        val now = System.currentTimeMillis()
        val db = writableDatabase
        db.beginTransaction()
        try {
            for (record in records) {
                val values = ContentValues().apply {
                    put("client_record_id", record.clientRecordId)
                    put("captured_at_millis", record.capturedAtMillis)
                    put("sent_at_millis", now)
                    put("outcome", outcomes[record.clientRecordId] ?: "sent")
                    put("payload", record.payload)
                    put("was_offline", if (record.wasOffline) 1 else 0)
                }
                db.insert(SENT_TABLE, null, values)
            }
            db.execSQL(
                """
                DELETE FROM $SENT_TABLE WHERE id NOT IN (
                    SELECT id FROM $SENT_TABLE ORDER BY sent_at_millis DESC, id DESC LIMIT ?
                )
                """.trimIndent(),
                arrayOf(SENT_HISTORY_LIMIT.toString()),
            )
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
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

data class QueuedRecord(
    val id: Long,
    val clientRecordId: String,
    val payload: String,
    val capturedAtMillis: Long,
    val wasOffline: Boolean,
)
