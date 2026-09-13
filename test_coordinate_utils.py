import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coordinate_utils import wgs84_to_utm


class CoordinateUtilsTests(unittest.TestCase):
    def test_zone_51_central_meridian_at_equator(self):
        easting, northing = wgs84_to_utm(123.0, 0.0)
        self.assertAlmostEqual(easting, 500000.0, places=3)
        self.assertAlmostEqual(northing, 0.0, places=3)

    def test_zone_51_north_hemisphere(self):
        easting, northing = wgs84_to_utm(123.0, 1.0)
        self.assertAlmostEqual(easting, 500000.0, places=3)
        self.assertGreater(northing, 110000.0)
        self.assertLess(northing, 112000.0)


if __name__ == "__main__":
    unittest.main()
