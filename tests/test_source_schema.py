"""Fast static tests. No Databricks workspace needed."""
import ast
import csv
import json
import re
import unittest
from collections import defaultdict
from decimal import Decimal
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ("00_verify_access", "01_ingest_bronze", "02_transform_silver", "03_build_gold", "04_validate_quality")
DEMO = ROOT / "data" / "demo_batch_2026_01"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def bronze_patterns():
    """Read the DATASETS entity -> pattern mapping from the Bronze notebook."""
    tree = ast.parse((ROOT / "notebooks" / "01_ingest_bronze.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "DATASETS":
            return ast.literal_eval(node.value)
    raise AssertionError("DATASETS not found in 01_ingest_bronze.py")


class RepositoryContractTest(unittest.TestCase):
    def test_notebook_sources_are_valid_python(self):
        for name in NOTEBOOKS:
            path = ROOT / "notebooks" / f"{name}.py"
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("# Databricks notebook source"))
            ast.parse(content, filename=str(path))

    def test_no_sensitive_files_are_committed(self):
        self.assertIn(".env", (ROOT / ".gitignore").read_text())

    def test_job_runs_every_notebook_in_order(self):
        job = (ROOT / "resources" / "novacart_pipeline.job.yml").read_text(encoding="utf-8")
        paths = re.findall(r"notebook_path:\s*\.\./notebooks/(\S+)\.py", job)
        self.assertEqual(paths, list(NOTEBOOKS))
        self.assertIn("project: dpe-azure-poc", job)
        self.assertIn("pause_status: PAUSED", job)

    def test_every_file_matches_exactly_one_bronze_pattern(self):
        patterns = bronze_patterns()
        files = [p for p in (ROOT / "data").rglob("*") if p.suffix in (".csv", ".json") and p.name != "manifest.json"]
        self.assertTrue(files)
        for path in files:
            matches = [entity for entity, pattern in patterns.items() if fnmatch(path.name, pattern)]
            self.assertEqual(len(matches), 1, f"{path.name} matches {matches}")


@unittest.skipUnless(DEMO.is_dir(), "demo batch not generated")
class DemoBatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = {name: read_csv(DEMO / f"{name}_2026_01_USD.csv") for name in
                 ("customers", "orders", "order_items", "payments", "website_sessions", "website_events")}
        cls.manifest = json.loads((DEMO / "manifest.json").read_text(encoding="utf-8"))

    def test_row_counts_match_manifest(self):
        self.assertEqual({k: len(v) for k, v in self.t.items()}, self.manifest["rows"])

    def test_new_order_totals_equal_sum_of_items(self):
        lines = defaultdict(Decimal)
        for item in self.t["order_items"]:
            lines[item["order_id"]] += Decimal(item["line_total_usd"])
        new_orders = [o for o in self.t["orders"] if o["record_month"] == "2026-01"]
        self.assertEqual(len(new_orders), self.manifest["new_orders"])
        for order in new_orders:
            self.assertEqual(Decimal(order["order_total_usd"]), lines[order["order_id"]], order["order_id"])

    def test_links_inside_batch(self):
        order_ids = {o["order_id"] for o in self.t["orders"]}
        session_ids = {s["session_id"] for s in self.t["website_sessions"]}
        self.assertTrue(all(i["order_id"] in order_ids for i in self.t["order_items"]))
        self.assertTrue(all(p["order_id"] in order_ids for p in self.t["payments"]))
        self.assertTrue(all(e["session_id"] in session_ids for e in self.t["website_events"]))

    def test_expected_net_revenue_change(self):
        sign = {"captured": 1, "refunded": -1}
        net = sum(Decimal(p["amount_usd"]) * sign.get(p["payment_status"], 0) for p in self.t["payments"])
        self.assertEqual(str(net), self.manifest["expected_net_revenue_change_usd"])


if __name__ == "__main__":
    unittest.main()
