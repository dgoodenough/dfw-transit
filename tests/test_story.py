"""The story page: every cited fact has a source, and the page template takes the data."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dfwt.network import Network  # noqa: E402
from dfwt import story  # noqa: E402


class StoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "dfwt", "templates", "story_facts.json"), encoding="utf-8") as f:
            cls.facts = json.load(f)

    def test_every_citation_has_a_source(self):
        src = self.facts["sources"]
        ids = [i for steps in self.facts["steps"].values() for _, ids in steps for i in ids]
        ids += [i for c in self.facts["charts"].values() for i in c.get("cites", [])]
        self.assertTrue(ids)
        for i in ids:
            self.assertIn(i, src)
            self.assertTrue(src[i]["source"] and src[i]["url"].startswith("http"), i)

    def test_template_takes_the_data(self):
        with open(os.path.join(ROOT, "dfwt", "templates", "story.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertEqual(html.count("/*__DATA__*/null"), 1)
        self.assertIn('href="map.html"', html)

    def test_connections_name_real_stations(self):
        names = story._station_index(Network.load("two_million"))
        for o, d, *_ in story.CONNECTIONS:
            self.assertIn(o, names)
            self.assertIn(d, names)

    def test_current_track_is_todays_system(self):
        net = Network.load("current_track")
        self.assertTrue(net.lines and all(ln.status == "existing" for ln in net.lines.values()))
        self.assertTrue(all(not ln.service for ln in net.lines.values()))   # today's frequencies
        ex = net.cfg["existing_year"]
        self.assertTrue(all(y <= ex or y >= 9999 for ln in net.lines.values() for y in ln.stop_years))
