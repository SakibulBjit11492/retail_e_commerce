# Databricks notebook source
# NovaCart PoC | 01: Append raw CSV/JSON files from a Unity Catalog volume to Bronze Delta tables.
#
# How new data arrives: drop a new file that matches the entity pattern into the raw/ folder,
# e.g. orders_2026_01_USD.csv next to orders_2025_USD.csv. Each run ingests only files that are
# not yet in Bronze (same file name + same modification time). Set force_reload=true to append
# everything again; Silver de-duplicates by business key, so revenue is never double-counted.

# COMMAND ----------
dbutils.widgets.text("catalog", "dpe_azure_poc", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Target schema")
dbutils.widgets.text("volume_schema", "", "Schema of the volume (empty = same as target schema)")
dbutils.widgets.text("volume", "landing", "Raw data volume")
dbutils.widgets.text("batch_id", "manual", "Batch ID (a job passes its run id)")
dbutils.widgets.dropdown("force_reload", "false", ["false", "true"], "Re-ingest already loaded files")

# COMMAND ----------
from fnmatch import fnmatch
from pyspark.sql import functions as F

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
VOLUME = dbutils.widgets.get("volume").strip()
VOLUME_SCHEMA = dbutils.widgets.get("volume_schema").strip() or SCHEMA
BATCH_ID = dbutils.widgets.get("batch_id").strip() or "manual"
FORCE_RELOAD = dbutils.widgets.get("force_reload").strip().lower() == "true"


def ident(value):
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"Invalid Unity Catalog identifier: {value!r}")
    return f"`{value}`"


PREFIX = f"{ident(CATALOG)}.{ident(SCHEMA)}"
RAW_DIR = f"/Volumes/{CATALOG}/{VOLUME_SCHEMA}/{VOLUME}/raw"

# entity -> file name pattern inside raw/
DATASETS = {
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
FILE_KEY = ["_source_file", "_source_file_modified_at"]

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {PREFIX}")
raw_files = [f for f in dbutils.fs.ls(RAW_DIR) if not f.name.endswith("/")]
print(f"Batch {BATCH_ID}: {len(raw_files)} file(s) in {RAW_DIR}; force_reload={FORCE_RELOAD}")

# COMMAND ----------
summary = []
for dataset, pattern in DATASETS.items():
    target = f"{PREFIX}.{ident('bronze_' + dataset)}"
    paths = sorted(f.path for f in raw_files if fnmatch(f.name, pattern))
    if not paths:
        summary.append((dataset, 0, "no file matches " + pattern))
        continue

    if pattern.endswith(".csv"):
        # All columns stay strings in Bronze ("as received"); typing happens in Silver.
        reader = spark.read.option("header", "true").option("inferSchema", "false").format("csv")
    else:
        reader = spark.read.option("multiLine", "true").format("json")

    df = (
        reader.load(paths)
        .select("*", F.col("_metadata.file_name").alias("_source_file"),
                F.col("_metadata.file_modification_time").alias("_source_file_modified_at"))
        .withColumn("_ingested_at_utc", F.current_timestamp())
        .withColumn("_load_batch_id", F.lit(BATCH_ID))
    )

    if spark.catalog.tableExists(target) and not FORCE_RELOAD:
        existing_cols = set(spark.table(target).columns)
        key = [c for c in FILE_KEY if c in existing_cols]
        already_loaded = spark.table(target).select(*key).distinct()
        df = df.join(already_loaded, key, "left_anti")

    rows = df.count()
    if rows == 0:
        summary.append((dataset, 0, "skipped: files already in Bronze"))
        continue

    files_loaded = [r["_source_file"] for r in df.select("_source_file").distinct().collect()]
    # mergeSchema lets new source columns arrive without deleting earlier Bronze records.
    df.write.format("delta").option("mergeSchema", "true").mode("append").saveAsTable(target)
    summary.append((dataset, rows, "appended from " + ", ".join(sorted(files_loaded))))

for dataset, rows, note in summary:
    print(f"{dataset:20s} {rows:>7,} rows  {note}")
print("Bronze ingestion complete. Run 02_transform_silver next.")
