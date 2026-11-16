"""Offline tests. The fixtures are small pages modelled on the text of the union's pages;
they check the parsing logic, not the live site.  Run:  python3 -m unittest discover -s tools
"""
import unittest

import scrape_marrakech as s

DAY_INDEX = """
<html><body><nav><h2>Navigation</h2><a href="/en">Home</a></nav>
<h1>On-duty pharmacies in Marrakech today</h1>
<p>Schedule period — From 31/10/2026 to 06/11/2026</p>
<section><h2>MEDINA</h2><p>2 pharmacies</p><p>From 31/10/2026 to 06/11/2026</p>
<p>From 9 AM to 10 PM without interruption</p><a href="/en/on-duty-pharmacies-marrakech/medina">On-duty pharmacies in Medina</a></section>
<section><h2>HAY CHARAF</h2><p>0 pharmacy</p><p>From 9 AM to 10 PM without interruption</p></section>
<section><h2>AÏN ITTI</h2><p>1 pharmacy</p><p>From 9 AM to 10 PM without interruption</p></section>
</body></html>
"""

NIGHT_INDEX = """
<h1>Night on-duty pharmacies in Marrakech</h1><p>Schedule period — From 14/11/2026 to 20/11/2026</p>
<h2>MEDINA</h2><p>1 pharmacy</p><p>From 14/11/2026 to 20/11/2026</p><p>From 10 PM to 9 AM without interruption</p>
<h2>DAOUDIAT</h2><p>3 pharmacies</p><p>From 10 PM to 9 AM without interruption</p>
<h2>HAY CHARAF</h2><p>0 pharmacy</p>
"""

MEDINA = """
<h1>On-duty pharmacies in Medina, Marrakech</h1>
<article><span>On duty</span><h2>Pharmacie KOUTOUBIA</h2>
<p>Av. Fatima Zohra R’mila, Marrakech MEDINA</p><p>From 9 AM to 10 PM without interruption</p>
<a href="tel:0524-38-10-72">0524-38-10-72</a><a href="/en/x/pharmacy/pharmacie-koutoubia">View Pharmacie KOUTOUBIA</a>
<a href="https://www.google.com/maps/dir/?api=1&amp;destination=31.627366,-7.993468">Directions</a></article>
<article><span>On duty</span><h2>Pharmacie SANTÉ ET BIEN-ÊTRE</h2>
<p>Route de l'Aéroport, à côté de la Clinique Internationale, Marrakech MEDINA</p><p>From 9 AM to 11 PM without interruption</p>
<a href="tel:0524378918">0524-37-89-18</a>
<a href="https://www.google.com/maps/dir/?api=1&destination=0,0">Directions</a></article>
<footer><p>Marrakech Pharmacies</p><h2>Navigation</h2><a href="/en">Home</a></footer>
"""

AIN_ITTI = """
<h2>Pharmacie EL HAMIDI</h2><p>26, Aïn Itti devant le cimetière de Bab lakhmis, Marrakech AÏN ITTI</p>
<p>From 9 AM to 10 PM without interruption</p><a href="tel:0524-30-73-50">0524-30-73-50</a>
<h2>Pharmacie DAR TOUNSI</h2><p>66, Biout El Boun, Marrakech AÏN ITTI</p><a href="tel:0524-32-96-52">x</a>
"""

PAGES = {
    s.DAY_URL: DAY_INDEX,
    s.NIGHT_URL: NIGHT_INDEX,
    s.DAY_URL + "/medina": MEDINA,
    s.DAY_URL + "/ain-itti": AIN_ITTI,
}


class ScrapeTests(unittest.TestCase):
    def test_index(self):
        idx = s.parse_index(s.parse_items(DAY_INDEX))
        self.assertEqual(idx["period"], ("2026-10-31", "2026-11-06"))
        self.assertEqual(idx["hours"], (9, "AM", 10, "PM"))
        self.assertEqual(idx["counts"], {"medina": 2, "hay-charaf": 0, "ain-itti": 1})

    def test_night_index(self):
        idx = s.parse_index(s.parse_items(NIGHT_INDEX))
        self.assertEqual(idx["period"], ("2026-11-14", "2026-11-20"))
        self.assertEqual(idx["counts"]["daoudiat"], 3)
        self.assertEqual(idx["hours"], (10, "PM", 9, "AM"))

    def test_district_cards(self):
        recs = s.parse_district(s.parse_items(MEDINA), "medina")
        self.assertEqual([r["name"] for r in recs], ["Koutoubia", "Santé Et Bien-Être"])
        k = recs[0]
        self.assertEqual(k["address"], "Av. Fatima Zohra R’mila")
        self.assertEqual(k["phone"], "0524-38-10-72")
        self.assertEqual((k["lat"], k["lng"]), (31.627366, -7.993468))
        self.assertEqual(k["district"], "المدينة")
        sb = recs[1]
        self.assertEqual(sb["phone"], "0524-37-89-18")
        self.assertIsNone(sb["lat"])  # 0,0 is treated as missing
        self.assertEqual(sb["hours"], (9, "AM", 11, "PM"))
        self.assertTrue(sb["address"].endswith("Clinique Internationale"))

    def test_hours_text(self):
        self.assertEqual(s.ar_hours((9, "AM", 10, "PM")), "من 9 صباحا إلى 10 ليلا")
        self.assertEqual(s.ar_hours((10, "PM", 9, "AM")), "من 10 ليلا إلى 9 صباحا")

    def test_build(self):
        data, warnings = s.build(lambda u: PAGES.get(u, ""), today="2026-11-14", pause=0)
        self.assertEqual(len(data["pharmacies"]), 4)
        self.assertEqual(data["dayFrom"], "2026-10-31")
        self.assertEqual(data["nightTo"], "2026-11-20")
        self.assertEqual(data["dayHours"], "من 9 صباحا إلى 10 ليلا")
        self.assertEqual(data["night"][1], {"district": "الداوديات", "count": 3})
        # a card with different hours keeps its own hours
        self.assertEqual(data["pharmacies"][1]["hours"], "من 9 صباحا إلى 11 ليلا")
        self.assertNotIn("hours", data["pharmacies"][0])
        # the Aïn Itti page lists 2 although the index says 1, and the day list is stale
        self.assertTrue(any("Aïn Itti" in w for w in warnings))
        self.assertTrue(any("not published a new day list" in w for w in warnings))

    def test_layout_change_is_detected(self):
        pages = dict(PAGES)
        pages[s.DAY_URL] = "<html><body>Maintenance</body></html>"
        data, warnings = s.build(lambda u: pages.get(u, ""), today="2026-11-14", pause=0)
        self.assertIsNone(data)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
