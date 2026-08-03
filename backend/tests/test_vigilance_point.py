"""Tests for the new point-based vigilance (dynamic departement + neighbours)."""
import asyncio
import unittest

import geo
import vigilance


class TestGeoLookup(unittest.TestCase):
    def test_point_in_polygon_known_cities(self):
        cases = [
            (43.095, -0.045, "65"),   # Lourdes
            (48.514, -2.765, "22"),   # Saint-Brieuc
            (48.117, -1.677, "35"),   # Rennes
            (48.856, 2.352, "75"),    # Paris
            (43.710, 7.262, "06"),    # Nice
        ]
        for lat, lon, expected in cases:
            with self.subTest(pt=(lat, lon)):
                self.assertEqual(geo.find_departement(lat, lon), expected)

    def test_neighbours_are_symmetric(self):
        # 22 and 35 must be mutual neighbours
        self.assertIn("35", geo.find_neighbours("22"))
        self.assertIn("22", geo.find_neighbours("35"))

    def test_out_of_france_returns_none(self):
        # Mid-Atlantic
        self.assertIsNone(geo.find_departement(45.0, -20.0))


class TestVigilanceForPoint(unittest.TestCase):
    def test_saint_brieuc_primary_and_neighbours(self):
        data = asyncio.run(vigilance.compute_vigilance_for_point(
            48.514, -2.765, zone_name="Saint-Brieuc",
        ))
        self.assertEqual(data["primary_id"], "22")
        self.assertEqual(data["primary_name"], "Côtes-d'Armor")
        self.assertEqual(data["zone_name"], "Saint-Brieuc")
        ids = [d["id"] for d in data["departements"]]
        # primary first
        self.assertEqual(ids[0], "22")
        # actual bordering depts
        self.assertIn("35", ids)
        self.assertIn("29", ids)
        self.assertIn("56", ids)
        # must NOT contain unrelated depts
        self.assertNotIn("65", ids)

    def test_fallback_when_outside_france(self):
        # Outside FR → historical Lourdes structure (no primary_id)
        data = asyncio.run(vigilance.compute_vigilance_for_point(45.0, -20.0))
        # compute_vigilance() has no primary_id key
        self.assertNotIn("primary_id", data)


if __name__ == "__main__":
    unittest.main()
