package ma.pharmagarde.marrakech

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.location.Location
import android.location.LocationManager
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

private const val ALL = "الكل"

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { App() }
    }
}

@Composable
fun App() {
    val ctx = LocalContext.current
    var schedule by remember { mutableStateOf<Schedule?>(null) }
    LaunchedEffect(Unit) { schedule = Repository.load(ctx) }

    val scheme = if (isSystemInDarkTheme()) {
        darkColorScheme(primary = Color(0xFF3DD392), onPrimary = Color(0xFF05261A))
    } else {
        lightColorScheme(primary = Color(0xFF0B7A4B), onPrimary = Color.White)
    }
    MaterialTheme(colorScheme = scheme) {
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
            Surface(Modifier.fillMaxSize()) {
                val s = schedule
                if (s == null) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                } else {
                    Home(s)
                }
            }
        }
    }
}

private fun fmt(iso: String) = iso.split("-").reversed().joinToString("/")

private fun km(aLat: Double, aLng: Double, bLat: Double, bLng: Double): Double {
    val r = 6371.0
    val dLat = Math.toRadians(bLat - aLat)
    val dLng = Math.toRadians(bLng - aLng)
    val h = sin(dLat / 2) * sin(dLat / 2) +
        cos(Math.toRadians(aLat)) * cos(Math.toRadians(bLat)) * sin(dLng / 2) * sin(dLng / 2)
    return 2 * r * atan2(sqrt(h), sqrt(1 - h))
}

@SuppressLint("MissingPermission")
private fun lastKnown(ctx: Context): Location? {
    val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    return lm.getProviders(true)
        .mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
        .maxByOrNull { it.time }
}

private fun open(ctx: Context, uri: Uri, action: String = Intent.ACTION_VIEW) {
    runCatching { ctx.startActivity(Intent(action, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}

@Composable
private fun Home(s: Schedule) {
    val ctx = LocalContext.current
    var tab by remember { mutableIntStateOf(0) }
    var query by remember { mutableStateOf("") }
    var district by remember { mutableStateOf(ALL) }
    var here by remember { mutableStateOf<Location?>(null) }

    val askLocation = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted.values.any { it }) {
            here = lastKnown(ctx)
            if (here == null) {
                Toast.makeText(ctx, "ما قدرتش نحدد موقعك. شعل GPS وعاود.", Toast.LENGTH_LONG).show()
            }
        }
    }

    val today = LocalDate.now()
    val dayOk = runCatching {
        !today.isBefore(LocalDate.parse(s.dayFrom)) && !today.isAfter(LocalDate.parse(s.dayTo))
    }.getOrDefault(false)

    val districts = remember(s) { listOf(ALL) + s.pharmacies.map { it.district }.distinct() }
    val rows = s.pharmacies
        .filter { district == ALL || it.district == district }
        .filter { query.isBlank() || "${it.name} ${it.district} ${it.address}".contains(query.trim(), ignoreCase = true) }
        .let { list ->
            val h = here
            if (h == null) list else list.sortedBy { p ->
                if (p.lat == null || p.lng == null) Double.MAX_VALUE
                else km(h.latitude, h.longitude, p.lat, p.lng)
            }
        }

    LazyColumn(
        modifier = Modifier.fillMaxSize().safeDrawingPadding(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text("صيدلية الحراسة · مراكش", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("اللائحة منقولة من نقابة صيادلة مراكش", style = MaterialTheme.typography.bodySmall)
        }
        item {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = if (dayOk) MaterialTheme.colorScheme.secondaryContainer
                    else MaterialTheme.colorScheme.errorContainer
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    text = if (dayOk) "لائحة النهار محينة: من ${fmt(s.dayFrom)} حتى ${fmt(s.dayTo)}."
                    else "تنبيه: لائحة النهار اللي عندي هي ديال ${fmt(s.dayFrom)} حتى ${fmt(s.dayTo)}، وماشي ديال اليوم. " +
                        "تاصل بالصيدلية قبل ما تمشي ليها.",
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
        item {
            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("حراسة النهار") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("حراسة الليل") })
            }
        }

        if (tab == 0) {
            item {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text("قلب على اسم الصيدلية ولا الحي") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedButton(
                    onClick = {
                        askLocation.launch(
                            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
                        )
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (here == null) "رتب حسب الأقرب ليا" else "مرتبة حسب الأقرب ليك") }
            }
            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(districts) { d ->
                        FilterChip(selected = district == d, onClick = { district = d }, label = { Text(d) })
                    }
                }
            }
            item { Text("${rows.size} صيدلية", style = MaterialTheme.typography.bodySmall) }
            items(rows, key = { it.name + it.phone }) { p -> PharmacyCard(p, s.dayHours, here) }
        } else {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        "حراسة الليل: من ${fmt(s.nightFrom)} حتى ${fmt(s.nightTo)}، ${s.nightHours}. " +
                            "كاين ${s.night.sumOf { it.count }} صيدلية. عندي غير العدد ديال كل حي، " +
                            "والأسماء والعناوين كتلقاهم عند النقابة.",
                        modifier = Modifier.padding(12.dp),
                    )
                }
            }
            items(s.night, key = { it.district }) { n ->
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(n.district)
                    Text(if (n.count == 1) "1 صيدلية" else "${n.count} صيدليات")
                }
            }
            item {
                Button(
                    onClick = { open(ctx, Uri.parse(s.nightSource)) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("شوف أسماء الصيدليات الليلية عند النقابة") }
            }
        }

        item {
            Text(
                "اللائحة كتتبدل كل أسبوع. تاصل بالصيدلية قبل ما تمشي ليها. فحالة الاستعجال: الوقاية المدنية 15.",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
    }
}

@Composable
private fun PharmacyCard(p: Pharmacy, defaultHours: String, here: Location?) {
    val ctx = LocalContext.current
    val distance = if (here != null && p.lat != null && p.lng != null)
        km(here.latitude, here.longitude, p.lat, p.lng) else null

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Text("Pharmacie ${p.name}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                }
                Text(
                    text = if (distance != null) "${"%.1f".format(distance)} كم" else p.district,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Text(p.address, style = MaterialTheme.typography.bodyMedium)
            }
            Text(p.hours ?: defaultHours, style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Button(onClick = {
                    open(ctx, Uri.parse("tel:" + p.phone.replace("-", "")), Intent.ACTION_DIAL)
                }) { Text("اتصل") }
                OutlinedButton(onClick = {
                    val uri = if (p.lat != null && p.lng != null)
                        Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}")
                    else
                        Uri.parse("https://www.google.com/maps/search/?api=1&query=" + Uri.encode("Pharmacie ${p.name} Marrakech"))
                    open(ctx, uri)
                }) { Text(if (p.lat != null) "الطريق" else "قلب فالخريطة") }
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Text(p.phone, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}
