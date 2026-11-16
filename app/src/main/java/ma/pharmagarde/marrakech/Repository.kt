package ma.pharmagarde.marrakech

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

data class Pharmacy(
    val name: String,
    val district: String,
    val address: String,
    val phone: String,
    val lat: Double?,
    val lng: Double?,
    val hours: String?,
)

data class NightCount(val district: String, val count: Int)

data class Schedule(
    val dayFrom: String,
    val dayTo: String,
    val dayHours: String,
    val nightFrom: String,
    val nightTo: String,
    val nightHours: String,
    val source: String,
    val nightSource: String,
    val pharmacies: List<Pharmacy>,
    val night: List<NightCount>,
)

object Repository {
    /**
     * رابط JSON ديال اللائحة المحينة (بنفس شكل pharmacies_marrakech.json).
     * خليه فارغ باش التطبيق يخدم غير بالمعطيات اللي داخل الأبليكاسيون.
     * مثال: "https://example.ma/pharmacies/marrakech.json"
     */
    const val REMOTE_URL = ""

    fun parse(text: String): Schedule {
        val o = JSONObject(text)
        val arr = o.getJSONArray("pharmacies")
        val pharmacies = (0 until arr.length()).map { i ->
            val p = arr.getJSONObject(i)
            Pharmacy(
                name = p.getString("name"),
                district = p.getString("district"),
                address = p.getString("address"),
                phone = p.getString("phone"),
                lat = if (p.isNull("lat")) null else p.getDouble("lat"),
                lng = if (p.isNull("lng")) null else p.getDouble("lng"),
                hours = if (p.isNull("hours")) null else p.getString("hours"),
            )
        }
        val n = o.getJSONArray("night")
        val night = (0 until n.length()).map { i ->
            val x = n.getJSONObject(i)
            NightCount(x.getString("district"), x.getInt("count"))
        }
        return Schedule(
            dayFrom = o.getString("dayFrom"),
            dayTo = o.getString("dayTo"),
            dayHours = o.getString("dayHours"),
            nightFrom = o.getString("nightFrom"),
            nightTo = o.getString("nightTo"),
            nightHours = o.getString("nightHours"),
            source = o.getString("source"),
            nightSource = o.getString("nightSource"),
            pharmacies = pharmacies,
            night = night,
        )
    }

    private fun fetch(url: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 8000
        return try {
            c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
    }

    /** كيختار اللائحة الأحدث بين: الإنترنت، النسخة المحفوظة، والنسخة اللي داخل التطبيق. */
    suspend fun load(ctx: Context): Schedule = withContext(Dispatchers.IO) {
        val candidates = mutableListOf<Schedule>()
        val cache = File(ctx.filesDir, "schedule.json")

        runCatching {
            ctx.assets.open("pharmacies_marrakech.json").bufferedReader().use { it.readText() }
        }.onSuccess { candidates += parse(it) }

        if (cache.exists()) runCatching { parse(cache.readText()) }.onSuccess { candidates += it }

        if (REMOTE_URL.isNotBlank()) {
            runCatching {
                val text = fetch(REMOTE_URL)
                val s = parse(text)
                cache.writeText(text)
                s
            }.onSuccess { candidates += it }
        }

        candidates.maxWith(compareBy<Schedule>({ it.nightTo }, { it.dayTo }))
    }
}
