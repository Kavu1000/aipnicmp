package la.aipnicmp.collector.ui

import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import la.aipnicmp.collector.R
import la.aipnicmp.collector.data.MeasurementStore
import la.aipnicmp.collector.data.RadioState
import la.aipnicmp.collector.data.RecordSummary
import la.aipnicmp.collector.databinding.ActivityRecordsBinding
import java.text.DateFormat
import java.util.Date
import java.util.Locale

/**
 * Every record this phone is holding, and every one it has sent.
 *
 * A counter cannot answer the questions a collector actually has — what did I
 * gather on that road, did any of it reach the server, and if the server
 * refused it, why. Those matter most in exactly the situation the counters
 * describe worst: a long drive through a dead zone, where nothing uploads for
 * hours and the screen shows a number that never moves.
 */
class RecordsActivity : AppCompatActivity() {

    private lateinit var binding: ActivityRecordsBinding
    private lateinit var store: MeasurementStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityRecordsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        title = getString(R.string.records_title)

        store = MeasurementStore(this)
        load()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    override fun onResume() {
        super.onResume()
        load()
    }

    private fun load() {
        val pending = store.listPending()
        val sent = store.listSent()

        val rows = mutableListOf<Row>()
        rows += Row.Header(getString(R.string.records_waiting, pending.size))
        if (pending.isEmpty()) {
            rows += Row.Note(getString(R.string.records_none_waiting))
        } else {
            // The offline count is the interesting number: those are the
            // readings no other method could have produced.
            val offline = pending.count { it.wasOffline }
            if (offline > 0) {
                rows += Row.Note(getString(R.string.records_waiting_summary, offline))
            }
            pending.forEach { rows += Row.Record(it) }
        }

        rows += Row.Header(getString(R.string.records_sent, sent.size))
        if (sent.isEmpty()) {
            rows += Row.Note(getString(R.string.records_none_sent))
        } else {
            sent.forEach { rows += Row.Record(it) }
        }

        binding.recordList.adapter = RowAdapter(rows)
    }

    private sealed interface Row {
        data class Header(val text: String) : Row
        data class Note(val text: String) : Row
        data class Record(val summary: RecordSummary) : Row
    }

    private inner class RowAdapter(private val rows: List<Row>) : BaseAdapter() {

        private val time = DateFormat.getTimeInstance(DateFormat.MEDIUM)
        private val dateTime = DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT)

        override fun getCount() = rows.size
        override fun getItem(position: Int) = rows[position]
        override fun getItemId(position: Int) = position.toLong()
        override fun getViewTypeCount() = 3
        override fun getItemViewType(position: Int) = when (rows[position]) {
            is Row.Header -> 0
            is Row.Note -> 1
            is Row.Record -> 2
        }

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val row = rows[position]
            val layout = when (row) {
                is Row.Header -> R.layout.item_record_header
                is Row.Note -> R.layout.item_record_note
                is Row.Record -> R.layout.item_record
            }
            val view = convertView ?: layoutInflater.inflate(layout, parent, false)

            when (row) {
                is Row.Header -> view.findViewById<TextView>(R.id.headerText).text = row.text
                is Row.Note -> view.findViewById<TextView>(R.id.noteText).text = row.text
                is Row.Record -> bind(view, row.summary)
            }
            return view
        }

        private fun bind(view: View, record: RecordSummary) {
            view.findViewById<TextView>(R.id.recordState).apply {
                text = getString(labelFor(record.state))
                setTextColor(colourFor(record.state))
            }

            view.findViewById<TextView>(R.id.recordTime).text = time.format(Date(record.capturedAtMillis))

            // The measurement itself, in the terms the proposal cares about:
            // what network, how strong, and how many cells were visible at all.
            val signal = record.rsrpDbm?.let { String.format(Locale.ROOT, "%.0f dBm", it) }
                ?: getString(R.string.records_no_signal_value)
            view.findViewById<TextView>(R.id.recordSignal).text = listOfNotNull(
                record.networkType ?: getString(R.string.records_no_network),
                signal,
                getString(R.string.records_cells, record.cellsVisible),
                record.operator,
            ).joinToString(" · ")

            view.findViewById<TextView>(R.id.recordPlace).text = String.format(
                Locale.ROOT,
                "%.5f, %.5f%s",
                record.lat,
                record.lon,
                record.accuracyM?.let { String.format(Locale.ROOT, " · ±%.0f m", it) } ?: "",
            )

            view.findViewById<TextView>(R.id.recordOffline).apply {
                visibility = if (record.wasOffline) View.VISIBLE else View.GONE
                setTextColor(getColor(R.color.calls_only))
            }

            val outcome = view.findViewById<TextView>(R.id.recordOutcome)
            if (record.outcome == null) {
                outcome.text = getString(R.string.records_waiting_row)
                outcome.setTextColor(getColor(R.color.muted))
            } else {
                val rejected = record.outcome.startsWith("rejected")
                outcome.text = if (rejected) {
                    record.outcome
                } else {
                    getString(
                        R.string.records_sent_at,
                        record.sentAtMillis?.let { dateTime.format(Date(it)) } ?: "",
                    )
                }
                outcome.setTextColor(getColor(if (rejected) R.color.primary else R.color.good))
            }
        }

        private fun labelFor(state: RadioState) = when (state) {
            RadioState.LTE_GOOD -> R.string.state_good
            RadioState.LTE_WEAK -> R.string.state_weak
            RadioState.REGISTERED_2G_3G -> R.string.state_calls_only
            RadioState.CELLS_VISIBLE_UNREGISTERED -> R.string.state_unusable
            RadioState.NO_CELL -> R.string.state_none
        }

        private fun colourFor(state: RadioState) = getColor(
            when (state) {
                RadioState.LTE_GOOD -> R.color.good
                RadioState.LTE_WEAK -> R.color.weak
                RadioState.REGISTERED_2G_3G -> R.color.calls_only
                RadioState.CELLS_VISIBLE_UNREGISTERED -> R.color.unusable
                RadioState.NO_CELL -> R.color.primary
            }
        )
    }
}
