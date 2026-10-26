# Databricks notebook source
# NovaCart PoC | 01: Append immutable raw CSV/JSON records from a Unity Catalog volume to Bronze Delta tables.

# COMMAND ----------
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Target schema")
dbutils.widgets.text("volume", "landing", "Raw data volume")
dbutils.widgets.text("batch_id", "2025_initial_load", "Batch ID")

# COMMAND ----------
from datetime import datetime, timezone
from pyspark.sql import functions as F

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
VOLUME = dbutils.widgets.get("volume").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()


def ident(value):
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"Invalid Unity Catalog identifier: {value!r}")
    return f"`{value}`"


PREFIX = f"{ident(CATALOG)}.{ident(SCHEMA)}"
RAW_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/raw"
DATASETS = {
    "customers": "customers_2025_USD.csv",
    "products": "products_2025_USD.csv",
    "orders": "orders_2025_USD.csv",
    "order_items": "order_items_2025_USD.csv",
    "payments": "payments_2025_USD.csv",
    "website_sessions": "website_sessions_2025_USD.csv",
    "website_events": "website_events_2025_USD.csv",
}
JSON_LOOKUPS = {
    "marketing_campaigns": "marketing_campaigns_2025.json",
    "shipping_methods": "shipping_methods_2025.json",
}

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {PREFIX}")
# Bronze is append-only; re-runs are handled by Silver deduplication using stable business keys.
for dataset, filename in {**DATASETS, **JSON_LOOKUPS}.items():
    path = f"{RAW_DIR}/{filename}"
    if filename.endswith(".csv"):
        df = spark.read.option("header", "true").option("inferSchema", "false").csv(path)
    else:
        df = spark.read.option("multiLine", "true").json(path)
    df = (
        df.withColumn("_source_file", F.lit(filename))
          .withColumn("_ingested_at_utc", F.current_timestamp())
          .withColumn("_load_batch_id", F.lit(BATCH_ID))
    )
    target = f"{PREFIX}.{ident('bronze_' + dataset)}"
    # Use mergeSchema so evolving source columns can be ingested without deleting prior Bronze records.
    df.write.format("delta").option("mergeSchema", "true").mode("append").saveAsTable(target)
    print(f"Bronze appended: {dataset} ({df.count()} source rows) -> {target}")
print("Bronze ingestion complete. Run 02_transform_silver.py next.")
