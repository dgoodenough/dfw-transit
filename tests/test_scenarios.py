"""The default scenario's tables: valid, and every line opens within the horizon."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, validate  # noqa: E402
from dfwt.network import Network  # noqa: E402


class DefaultScenarioTests(unittest.TestCase):
    def test_default_scenario_is_valid_and_opens_by_the_horizon(self):
        name = config.load()["default_scenario"]
        net = Network.load(name)
        found = validate.run(net)
        self.assertEqual([f for f in found if f[0] == "error"], [])
        self.assertEqual([f[2] for f in found if f[1] == "PAST_HORIZON"], [])
        self.assertEqual(validate.islands(net), {})


if __name__ == "__main__":
    unittest.main()
