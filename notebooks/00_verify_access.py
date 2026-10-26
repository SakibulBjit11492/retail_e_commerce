# Databricks notebook source
# NovaCart PoC | 00: Verify catalog/schema/volume configuration and raw files before ingestion.

# COMMAND ----------
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Schema")
dbutils.widgets.text("volume", "landing", "Landing volume")

# COMMAND ----------
from fnmatch import fnmatch

catalog, schema, volume = (dbutils.widgets.get(x).strip() for x in ("catalog", "schema", "volume"))
raw_dir = f"/Volumes/{catalog}/{schema}/{volume}/raw"
print("Checking Unity Catalog volume and raw files:", raw_dir)

# Same file patterns as 01_ingest_bronze. Every entity needs at least one file
# (e.g. the initial 2025 file); later batches such as orders_2026_01_USD.csv are picked up automatically.
PATTERNS = {
    "customers": "customers_*.csv",
    "products": "products_*.csv",
    "orders": "orders_*.csv",
    "order_items": "order_items_*.csv",
    "payments": "payments_*.csv",
    "website_sessions": "website_sessions_*.csv",
    "website_events": "website_events_*.csv",
    "marketing_campaigns": "marketing_campaigns_*.json",
    "shipping_methods": "shipping_methods_*.json",
}

files = [f for f in dbutils.fs.ls(raw_dir) if not f.name.endswith("/")]
for item in files:
    print(f"  {item.name:45s} {item.size:>10,} bytes")

missing = []
for entity, pattern in PATTERNS.items():
    matched = [f.name for f in files if fnmatch(f.name, pattern)]
    print(f"{entity:20s} -> {len(matched)} file(s) {matched}")
    if not matched:
        missing.append(entity)

assert not missing, f"No raw file found for: {missing}. Upload NOVACART_MINI_V2 into {raw_dir} first."
print("Storage access validated. You can now run 01_ingest_bronze.")
