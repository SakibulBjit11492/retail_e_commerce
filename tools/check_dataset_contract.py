"""Validate the separate NOVACART_MINI_V2 CSV package before it is uploaded to Azure.

Usage: python tools/check_dataset_contract.py "path/to/NOVACART_MINI_V2_2025_USD"
Requires Python 3.10+, no third-party dependencies.
"""
import csv
import json
import sys
from pathlib import Path

FILES = {
    "customers": ("customer_id", "signup_date", "country_code", "customer_tier"),
    "products": ("product_id", "product_name", "category", "list_price_usd", "unit_cost_usd"),
    "orders": ("order_id", "order_datetime", "customer_id", "order_status", "sales_channel", "currency"),
    "order_items": ("order_item_id", "order_id", "product_id", "quantity", "line_total_usd"),
    "payments": ("payment_id", "order_id", "payment_status", "amount_usd", "currency"),
    "website_sessions": ("session_id", "session_start", "sales_channel"),
    "website_events": ("event_id", "session_id", "event_type", "event_datetime", "product_id"),
}


def check_folder(directory: Path):
    if not directory.is_dir():
        raise FileNotFoundError(f"Missing dataset directory: {directory}")
    for entity, columns in FILES.items():
        path = directory / f"{entity}_2025_USD.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = set(columns) - set(reader.fieldnames or [])
            if missing:
                raise AssertionError(f"{entity}: missing columns {sorted(missing)}")
            rows = list(reader)
        if not rows:
            raise AssertionError(f"{entity}: empty source")
        assert all(row.get("dataset_tag") == "NOVACART_MINI_V2" for row in rows), f"{entity}: incorrect tag"
        print(f"PASS: {path.name} ({len(rows):,} rows)")
    for filename in ("marketing_campaigns_2025.json", "shipping_methods_2025.json"):
        data = json.loads((directory / filename).read_text(encoding="utf-8"))
        assert isinstance(data, list) and data, f"Invalid JSON lookup: {filename}"
        print(f"PASS: {filename} ({len(data):,} objects)")
    print("Source contract validated; dirty data is intentionally retained for Silver.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/check_dataset_contract.py DATASET_DIRECTORY")
    check_folder(Path(sys.argv[1]))
