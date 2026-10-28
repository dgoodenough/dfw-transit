import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metro import webpage  # noqa: E402


class WebpageTests(unittest.TestCase):
    def test_simplify_keeps_ends_and_corners(self):
        pts = [(0, 0), (1, 0.00001), (2, 0), (2, 1)]
        self.assertEqual(webpage._simplify(pts, 0.001), [(0, 0), (2, 0), (2, 1)])

    def test_summary_reads_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "report.md"), "w", encoding="utf-8") as f:
                f.write("# Generated network: Somewhere\n\n**Data warnings:** jobs missing; more\n\n"
                        "## Summary\n\n- **3 lines, 10 km**\n- `dfwt validate`: 0 errors\n\n## 1. Next\n- not this\n")
            s = webpage._summary(d)
        self.assertEqual(s["title"], "Generated network: Somewhere")
        self.assertEqual(s["warn"], "jobs missing; more")
        self.assertEqual(s["bullets"], ["3 lines, 10 km", "dfwt validate: 0 errors"])

    def test_page_embeds_every_generated_network(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated")
        if not os.path.isdir(root):
            self.skipTest("no generated networks")
        with tempfile.TemporaryDirectory() as d:
            path, data = webpage.write(out_path=os.path.join(d, "g.html"))
            html = open(path, encoding="utf-8").read()
        self.assertNotIn("/*__DATA__*/null", html)
        self.assertTrue(data and all(n["lines"] for n in data))


if __name__ == "__main__":
    unittest.main()
