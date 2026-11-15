"""Feature 03/04 service and HTTP contracts; runnable with unittest or pytest."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.services.discovery_service import compare_periods, discovery, findings, history, result_identity
from app.api.routes import unified
from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = json.loads((ROOT / "frontend/public/snapshots/yangon-2015-2024-temperature.json").read_text(encoding="utf-8"))
RAW = json.loads((Path(__file__).resolve().parents[1] / "fixtures/v1_yangon_2015_2025_live_2026-11-13.json").read_text(encoding="utf-8"))
Q = {"variable": "temperature", "latitude": 16.8661, "longitude": 96.1951, "start_date": "2015-01-01", "end_date": "2025-01-01"}
W = {"first_start_year": 2015, "first_end_year": 2019, "second_start_year": 2020, "second_end_year": 2024}

class DiscoveryContractTests(unittest.TestCase):
    def setUp(self):
        self.a = copy.deepcopy(SNAPSHOT)

    def test_calendar_gaps_and_excluded_values(self):
        a = self.a
        a["annual"] = [a["annual"][0], {**a["annual"][2], "eligible": False, "value": 0, "reasons": ["partial_calendar_year"]}]
        a["series"] = [{"date": "2015-01-01", "value": 0}, {"date": "2015-03-01", "value": 9, "usable": False, "status": "insufficient_support"}]
        h = history(a)
        self.assertEqual(len(h["annual"]), 10)
        self.assertEqual(len(h["monthly"]), 120)
        self.assertEqual(h["annual"][1]["status"], "missing")
        self.assertEqual(h["annual"][2]["value"], 0)
        self.assertEqual(h["annual"][2]["status"], "excluded")
        self.assertEqual([p["value"] for p in h["monthly"][:4]], [0, None, None, None])
        self.assertEqual(h["monthly"][2]["status"], "withheld")
        self.assertFalse(h["interpolated"])

    def test_empty_monthly_catalog_and_unsupported_monthly_product(self):
        self.a["series"] = []
        h = history(self.a)
        self.assertTrue(h["monthly_available"])
        self.assertEqual(len(h["monthly"]), 120)
        self.assertTrue(all(p["value"] is None for p in h["monthly"]))
        self.a["series_definition"] = None
        self.assertEqual(history(self.a)["monthly"], [])
        self.assertFalse(history(self.a)["monthly_available"])

    def test_leap_year_and_end_exclusive_calendar(self):
        self.a["period"] = {"start": "2020-02-01", "end_exclusive": "2020-04-01"}
        h = history(self.a)
        self.assertEqual([p["date"] for p in h["monthly"]], ["2020-02", "2020-03"])
        self.assertEqual([p["date"] for p in h["annual"]], ["2020"])

    def test_identity_tracks_values_and_product_not_cache(self):
        original = result_identity(self.a)
        self.a.update(cache={"hit": True, "retrieved_at": "new"}, data_status="cached_nasa_retrieval")
        self.assertEqual(result_identity(self.a), original)
        self.a["annual"][0]["value"] += 1
        self.assertNotEqual(result_identity(self.a), original)
        a = copy.deepcopy(SNAPSHOT)
        a["dataset"]["version"] = "new product"
        self.assertNotEqual(result_identity(a), original)

    def test_findings_never_upgrade_inference(self):
        cases = [("statistical_inference", .2, True, "increasing"), ("statistical_inference", -.2, True, "decreasing"),
                 ("statistical_inference", .2, False, "not_detected"), ("descriptive_slope", .2, True, "descriptive"),
                 ("annual_summaries_only", None, True, "unavailable")]
        for level, slope, significant, expected in cases:
            with self.subTest(kind=expected):
                a = copy.deepcopy(SNAPSHOT)
                a["trend"].update(result_level=level, slope=slope)
                a["trend"]["mann_kendall"]["is_statistically_significant"] = significant
                f = findings(a)
                self.assertEqual(f["kind"], expected)
                if expected in ("unavailable", "descriptive"):
                    self.assertIsNone(f["test"])
                    self.assertIsNone(f["confidence_interval"])
                if slope is not None:
                    self.assertAlmostEqual(f["per_decade"], slope * 10)
                self.assertIn("not a forecast", f["limitations"][0])

    def test_seasonal_ndvi_method_preserved(self):
        self.a["trend"]["method"] = "seasonal_kendall"
        f = findings(self.a)
        self.assertEqual(f["slope_method"], "Seasonal Sen slope")
        self.assertEqual(f["test_method"], "Seasonal Kendall")

    def test_seasonal_ndvi_does_not_expose_an_annual_fitted_change(self):
        self.a["variable"]["id"] = "ndvi"
        self.a["trend"]["method"] = "seasonal_kendall"

        seasonal = findings(self.a)

        self.assertIsNone(seasonal["fitted_change"])
        self.a["trend"]["method"] = "mann_kendall"
        annual = findings(self.a)
        expected = self.a["trend"]["slope"] * (
            max(self.a["trend"]["eligible_years"]) - min(self.a["trend"]["eligible_years"])
        )
        self.assertAlmostEqual(annual["fitted_change"], expected)

    def test_period_means_not_sum_of_yearly_totals(self):
        for p in self.a["annual"]:
            p["value"] = 10 if p["year"] <= 2019 else 20
        self.a["annual"][0].update(eligible=False, value=999, reasons=["insufficient_valid_months"])
        self.a["variable"]["id"] = "precipitation"
        self.a["units"]["annual_value"] = "mm/year"
        r = compare_periods(self.a, 2015, 2019, 2020, 2024)
        self.assertEqual((r["first"]["mean"], r["second"]["mean"], r["difference"]), (10, 20, 10))
        self.assertEqual(r["first"]["count"], 4)
        self.assertEqual(r["units"], "mm/year")

    def test_percentages_compared_in_percentage_points(self):
        for variable in ("relative_humidity", "extreme_heat"):
            with self.subTest(variable=variable):
                self.a["variable"]["id"] = variable
                self.assertEqual(compare_periods(self.a, 2015, 2019, 2020, 2024)["units"], "percentage points")

    def test_no_eligible_values_stay_unavailable(self):
        for p in self.a["annual"]:
            if p["year"] <= 2019:
                p["eligible"] = False
        r = compare_periods(self.a, 2015, 2019, 2020, 2024)
        self.assertEqual(r["status"], "unavailable")
        self.assertIsNone(r["difference"])
        self.assertIsNone(r["first"]["mean"])

    def test_invalid_windows(self):
        for windows in [(2019, 2015, 2020, 2024), (2015, 2020, 2020, 2024), (2014, 2019, 2020, 2024)]:
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                compare_periods(self.a, *windows)

    def test_api_cache_identity_and_comparison(self):
        calls = []
        async def fake(request, path, params):
            calls.append(path)
            return RAW["temperature_trend"]
        with patch.object(unified, "_call_v1", fake), TestClient(create_app(Settings(_env_file=None, ee_project_id="test"))) as client:
            response = client.get("/api/v2/analysis", params=Q)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(len(body["discovery"]["history"]["monthly"]), 120)
            identity = body["discovery"]["analysis_id"]
            compared = client.get("/api/v2/period-comparison", params={**Q, **W, "analysis_id": identity})
            self.assertEqual(compared.status_code, 200, compared.text)
            self.assertEqual(compared.json()["analysis_id"], identity)
            self.assertTrue(compared.json()["cache"]["hit"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(client.get("/api/v2/period-comparison", params={**Q, **W, "analysis_id": "0" * 64}).status_code, 409)
            calls.clear()
            invalid = client.get("/api/v2/period-comparison", params={**Q, **W, "first_end_year": 2020, "analysis_id": identity})
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(calls, [])

    def test_all_six_products(self):
        for name in ("temperature", "relative_humidity", "precipitation", "ndvi", "soil_moisture-gldas_2_1_noah_0_10cm", "extreme_heat"):
            with self.subTest(product=name):
                a = json.loads((ROOT / f"frontend/public/snapshots/yangon-2015-2024-{name}.json").read_text(encoding="utf-8"))
                r = discovery(a)
                self.assertEqual(len(r["analysis_id"]), 64)
                self.assertEqual(r["history"]["annual_units"], a["units"]["annual_value"])
                self.assertEqual(r["findings"]["slope"], (a["trend"] or {}).get("slope"))

if __name__ == "__main__":
    unittest.main()
