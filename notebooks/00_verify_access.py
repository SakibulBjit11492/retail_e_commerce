# Databricks notebook source
# NovaCart PoC | 00: Verify catalog/schema/volume configuration before the first ingestion.

# COMMAND ----------
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Schema")
dbutils.widgets.text("volume", "landing", "Landing volume")

# COMMAND ----------
catalog, schema, volume = (dbutils.widgets.get(x).strip() for x in ("catalog", "schema", "volume"))
raw_dir = f"/Volumes/{catalog}/{schema}/{volume}/raw"
print("Checking Unity Catalog and raw files:", raw_dir)
print("Available catalogs:")
spark.sql("SHOW CATALOGS").show(truncate=False)
files = dbutils.fs.ls(raw_dir)
for item in files:
    print(item.name, item.size, "bytes")
assert len(files) >= 9, "Expected 7 CSV + 2 JSON; upload NOVACART_MINI_V2 first"
print("Storage access validated. You can now run 01_ingest_bronze.py")
