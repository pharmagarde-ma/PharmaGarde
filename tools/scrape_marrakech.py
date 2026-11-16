#!/usr/bin/env python3
"""Fetch the Marrakech on-duty pharmacy schedule from the Pharmacists' Union site
and write the JSON file the Android app reads.

Only the Python standard library is used.

    python3 tools/scrape_marrakech.py --out data/marrakech.json
    python3 tools/scrape_marrakech.py --dump-dir /tmp/raw     # also save raw HTML for debugging

Exit codes: 0 ok (warnings are printed), 1 warnings with --strict, 2 nothing usable found.
When the exit code is not 0 the output file is left untouched.

Before running this on a schedule, check the site's legal notice and ask the union for permission.
"""
import argparse
import collections
import json
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://www.syndicat-pharmaciens-marrakech.com"
DAY_URL = BASE + "/en/on-duty-pharmacies-marrakech"
NIGHT_URL = BASE + "/en/on-duty-pharmacies-marrakech-night"
SOURCE_AR = BASE + "/ar/pharmacies-de-garde-marrakech"
NIGHT_SOURCE_AR = BASE + "/ar/pharmacies-de-garde-marrakech-nuit"
USER_AGENT = "PharmaGardeMarrakech/1.0 (weekly schedule sync)"

# slug, English name on the site, Arabic name shown in the app
DISTRICTS = [
    ("medina", "Medina", "المدينة"),
    ("grand-gueliz", "Grand Gueliz", "جليز الكبير"),
    ("daoudiat", "Daoudiat", "الداوديات"),
    ("hay-charaf", "Hay Charaf", "حي الشرف"),
    ("hay-dar-esaada", "Hay Dar Esaada", "حي دار السعادة"),
    ("hay-al-izdihar", "Hay Al Izdihar", "حي الإزدهار"),
    ("hay-al-fadl", "Hay Al Fadl", "حي الفضل"),
    ("sidi-ghanem-azzouzia", "Sidi Ghanem Azzouzia", "سيدي غانم العزوزية"),
    ("targa", "Targa", "تاركة"),
    ("hay-hassani", "Hay Hassani", "الحي الحسني"),
    ("ain-itti", "Aïn Itti", "عين إيطي"),
    ("nakhil-sud", "Nakhil Sud", "النخيل الجنوبي"),
    ("sidi-youssef", "Sidi Youssef", "سيدي يوسف"),
    ("lamhamid", "Lamhamid", "المحاميد"),
]


def norm(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().upper()


EN_TO_SLUG = {norm(en): slug for slug, en, _ in DISTRICTS}
SLUG_TO_AR = {slug: ar for slug, _, ar in DISTRICTS}
SLUG_TO_EN = {slug: en for slug, en, _ in DISTRICTS}

BLOCK = {"p", "div", "li", "ul", "ol", "section", "article", "br", "tr", "td", "th",
         "span_block", "header", "footer", "nav", "main", "table"}


class Collector(HTMLParser):
    """Turns a page into a flat list of ("h1"|"h2"|"h3"|"text"|"link", value) items."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self._buf = []
        self._skip = 0
        self._heading = None

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if text:
            self.items.append((self._heading or "text", text))

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag in ("h1", "h2", "h3"):
            self._flush()
            self._heading = tag
        elif tag == "a":
            self._flush()
            href = dict(attrs).get("href")
            if href:
                self.items.append(("link", href))
        elif tag in BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag in ("h1", "h2", "h3"):
            self._flush()
            self._heading = None
        elif tag == "a" or tag in BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def parse_items(html):
    c = Collector()
    c.feed(html)
    c.close()
    return c.items


PERIOD_RE = re.compile(r"From\s+(\d{2})/(\d{2})/(\d{4})\s+to\s+(\d{2})/(\d{2})/(\d{4})", re.I)
HOURS_RE = re.compile(r"(\d{1,2})\s*(AM|PM)\s*to\s*(\d{1,2})\s*(AM|PM)", re.I)
DEST_RE = re.compile(r"destination=(-?\d+\.\d+),\s*(-?\d+\.\d+)")
PHONE_RE = re.compile(r"0\d{3}-\d{2}-\d{2}-\d{2}")
NOISE = {"on duty", "open", "directions", "view details", "closed"}


def iso(d, m, y):
    return f"{y}-{m}-{d}"


def parse_hours(text):
    m = HOURS_RE.search(text)
    if not m:
        return None
    return (int(m.group(1)), m.group(2).upper(), int(m.group(3)), m.group(4).upper())


def ar_time(h, ap):
    if ap == "AM":
        return "منتصف الليل" if h == 12 else f"{h} صباحا"
    if h == 12:
        return "12 زوالا"
    return f"{h} مساء" if h <= 8 else f"{h} ليلا"


def ar_hours(h):
    return f"من {ar_time(h[0], h[1])} إلى {ar_time(h[2], h[3])}"


def fmt_phone(raw):
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}-{digits[8:]}"
    return raw.strip()


def parse_index(items):
    """Schedule period, the most common opening hours, and the pharmacy count per district."""
    period = None
    hours = collections.Counter()
    counts = {}
    for i, (kind, text) in enumerate(items):
        if kind == "text":
            m = PERIOD_RE.search(text)
            if m and period is None:
                period = (iso(m.group(1), m.group(2), m.group(3)), iso(m.group(4), m.group(5), m.group(6)))
            h = parse_hours(text)
            if h:
                hours[h] += 1
        elif kind == "h2":
            slug = EN_TO_SLUG.get(norm(text))
            if slug:
                for kind2, t2 in items[i + 1:i + 6]:
                    m = re.match(r"(\d+)\s+pharmac", t2, re.I)
                    if kind2 == "text" and m:
                        counts[slug] = int(m.group(1))
                        break
    common = hours.most_common(1)[0][0] if hours else None
    return {"period": period, "hours": common, "counts": counts}


def clean_address(text, slug):
    en = SLUG_TO_EN[slug]
    text = re.sub(r",?\s*Marrakech\s*" + re.escape(en) + r"\s*$", "", text, flags=re.I)
    text = re.sub(r",?\s*Marrakech\s+[A-ZÀ-Ý' ]{3,}$", "", text)
    return text.strip(" ,")


def display_name(name):
    name = re.sub(r"^pharmacie\s+", "", name, flags=re.I).strip()
    return name.title() if name.isupper() else name


def parse_district(items, slug):
    recs = []
    cur = None
    for kind, text in items:
        if kind == "h2":
            if re.match(r"pharmacie\b", text, re.I):
                cur = {"name": display_name(text), "district": SLUG_TO_AR[slug], "address": None,
                       "phone": None, "lat": None, "lng": None, "hours": None}
                recs.append(cur)
            else:
                cur = None
            continue
        if cur is None:
            continue
        if kind == "link":
            if text.lower().startswith("tel:"):
                cur["phone"] = cur["phone"] or fmt_phone(text[4:])
            m = DEST_RE.search(text)
            if m:
                lat, lng = float(m.group(1)), float(m.group(2))
                if (lat, lng) != (0.0, 0.0):
                    cur["lat"], cur["lng"] = lat, lng
            continue
        if kind != "text":
            continue
        h = parse_hours(text)
        if h:
            cur["hours"] = h
            continue
        low = text.lower()
        if low in NOISE or low.startswith("view ") or low.startswith("no on-duty"):
            continue
        if PHONE_RE.fullmatch(text):
            cur["phone"] = cur["phone"] or text
            continue
        if cur["address"] is None:
            cur["address"] = clean_address(text, slug)
    return recs


def fetch(url, dump_dir=None, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", errors="replace")
            if dump_dir:
                Path(dump_dir).mkdir(parents=True, exist_ok=True)
                name = re.sub(r"[^a-z0-9]+", "_", url.split("//", 1)[1].lower()).strip("_")
                (Path(dump_dir) / (name + ".html")).write_text(html, encoding="utf-8")
            return html
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}: {last}")


def build(fetch_fn, today=None, pause=0.8):
    """Returns (data, warnings). data is None when nothing usable was found."""
    today = today or date.today().isoformat()
    warnings = []

    day_index = parse_index(parse_items(fetch_fn(DAY_URL)))
    night_index = parse_index(parse_items(fetch_fn(NIGHT_URL)))

    pharmacies = []
    for slug, _, _ in DISTRICTS:
        expected = day_index["counts"].get(slug)
        if expected == 0:
            continue
        time.sleep(pause)
        recs = parse_district(parse_items(fetch_fn(f"{DAY_URL}/{slug}")), slug)
        if expected is not None and len(recs) != expected:
            warnings.append(f"{SLUG_TO_EN[slug]}: the index page says {expected}, the district page lists {len(recs)}")
        pharmacies += recs

    if not pharmacies or not day_index["period"]:
        return None, ["no pharmacies or no schedule period found: the page layout probably changed"]

    default_hours = day_index["hours"] or (9, "AM", 10, "PM")
    out_pharmacies = []
    for r in pharmacies:
        if not r["phone"]:
            warnings.append(f"no phone number for {r['name']} ({r['district']})")
        if not r["address"]:
            warnings.append(f"no address for {r['name']} ({r['district']})")
        item = {"name": r["name"], "district": r["district"], "address": r["address"] or "",
                "phone": r["phone"] or "", "lat": r["lat"], "lng": r["lng"]}
        if r["hours"] and r["hours"] != default_hours:
            item["hours"] = ar_hours(r["hours"])
        out_pharmacies.append(item)

    night = [{"district": SLUG_TO_AR[s], "count": n}
             for s, _, _ in DISTRICTS for n in [night_index["counts"].get(s, 0)] if n > 0]
    if not night_index["period"]:
        warnings.append("night schedule period not found")

    day_from, day_to = day_index["period"]
    night_from, night_to = night_index["period"] or ("", "")
    if day_to < today:
        warnings.append(f"the union has not published a new day list yet (it ends {day_to})")
    if night_to and night_to < today:
        warnings.append(f"the union has not published a new night list yet (it ends {night_to})")

    data = {
        "city": "Marrakech",
        "source": SOURCE_AR,
        "nightSource": NIGHT_SOURCE_AR,
        "dayFrom": day_from,
        "dayTo": day_to,
        "dayHours": ar_hours(default_hours),
        "nightFrom": night_from,
        "nightTo": night_to,
        "nightHours": ar_hours(night_index["hours"] or (10, "PM", 9, "AM")),
        "night": night,
        "pharmacies": out_pharmacies,
    }
    return data, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="app/src/main/assets/pharmacies_marrakech.json")
    ap.add_argument("--dump-dir", help="save every fetched page here")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    try:
        data, warnings = build(lambda u: fetch(u, args.dump_dir))
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 2

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if data is None:
        return 2
    if warnings and args.strict:
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(data['pharmacies'])} pharmacies, day {data['dayFrom']}..{data['dayTo']}, "
          f"night {data['nightFrom']}..{data['nightTo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
