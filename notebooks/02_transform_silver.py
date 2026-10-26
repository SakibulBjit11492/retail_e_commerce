# Databricks notebook source
# NovaCart PoC | 02: Clean, standardize, repair keys, deduplicate, and quarantine records in Silver.

# COMMAND ----------
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Target schema")

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()


def ident(v):
    if not v or not v.replace("_", "").isalnum():
        raise ValueError(f"Invalid Unity Catalog identifier: {v!r}")
    return f"`{v}`"


PREFIX = f"{ident(CATALOG)}.{ident(SCHEMA)}"


def get(name):
    return spark.table(f"{PREFIX}.{ident('bronze_' + name)}")


def money(name):
    return F.expr(f"try_cast(`{name}` as decimal(18,2))")


def timestamp(name):
    # This generated dataset contains both YYYY-MM-DD and US-style MM/DD/YYYY timestamps.
    return F.coalesce(
        F.expr(f"try_to_timestamp(`{name}`, 'yyyy-MM-dd HH:mm:ss')"),
        F.expr(f"try_to_timestamp(`{name}`, 'MM/dd/yyyy HH:mm:ss')"),
    )


def latest(df, id_col):
    # Keep the newest version of each business key. File names carry the data period
    # (orders_2025_USD.csv < orders_2026_01_USD.csv), so the later period wins; for the same file
    # name, the most recently modified upload wins. Re-ingesting old files (force_reload) therefore
    # never overwrites newer data, e.g. an order whose status later changed to 'returned'.
    w = Window.partitionBy(id_col).orderBy(
        F.col("_source_file").desc(),
        F.col("_source_file_modified_at").desc_nulls_last(),
        F.col("_ingested_at_utc").desc(),
        F.col("_load_batch_id").desc(),
    )
    return df.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")


def save(name, df):
    target = f"{PREFIX}.{ident('silver_' + name)}"
    (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target))
    print("Silver materialized:", target, df.count(), "rows")


spark.conf.set("spark.sql.session.timeZone", "UTC")

# COMMAND ----------
customers = (
    latest(get("customers"), "customer_id")
    .withColumn("signup_date", F.to_date("signup_date"))
    .withColumn("country_code", F.upper(F.trim("country_code")))
    .withColumn("customer_tier", F.lower(F.trim("customer_tier")))
    .filter(F.col("customer_id").isNotNull() & (F.trim("customer_id") != ""))
)
save("customers", customers)

products = (
    latest(get("products"), "product_id")
    .withColumn("list_price_usd", money("list_price_usd"))
    .withColumn("unit_cost_usd", money("unit_cost_usd"))
    .filter(F.col("product_id").isNotNull() & (F.trim("product_id") != ""))
)
save("products", products)

sessions = (
    latest(get("website_sessions"), "session_id")
    .withColumn("session_start", timestamp("session_start"))
    .withColumn("customer_id", F.when(F.trim("customer_id") == "", None).otherwise(F.col("customer_id")))
    .withColumn("order_id", F.when(F.trim("order_id") == "", None).otherwise(F.col("order_id")))
)
save("website_sessions", sessions)

# COMMAND ----------
# Recover the intentionally blank order customer_id from a linked session.
session_customers = sessions.select("session_id", F.col("customer_id").alias("session_customer_id"))
orders = (
    latest(get("orders"), "order_id")
    .join(session_customers, "session_id", "left")
    .withColumn("customer_id", F.coalesce(F.when(F.trim("customer_id") == "", None).otherwise(F.col("customer_id")), "session_customer_id"))
    .drop("session_customer_id")
    .withColumn("order_datetime", timestamp("order_datetime"))
    .withColumn("raw_status", F.lower(F.trim("order_status")))
    .withColumn("order_status", F.when(F.col("raw_status").isin("paid", "completed", "complete"), "paid")
                              .when(F.col("raw_status").isin("cancelled", "canceled"), "cancelled")
                              .when(F.col("raw_status").isin("returned", "return"), "returned")
                              .otherwise("unknown"))
    .drop("raw_status")
    .withColumn("order_total_usd", money("order_total_usd"))
    .withColumn("currency", F.upper(F.trim("currency")))
)
valid_customers = customers.select("customer_id").distinct()
invalid_orders = orders.filter(F.col("order_datetime").isNull() | F.col("customer_id").isNull() | (F.col("order_status") == "unknown"))
invalid_fk_orders = orders.join(valid_customers, "customer_id", "left_anti")
reject_order_ids = invalid_orders.select("order_id").unionByName(invalid_fk_orders.select("order_id")).distinct()
save("rejected_orders", orders.join(reject_order_ids, "order_id", "inner"))
orders = orders.join(reject_order_ids, "order_id", "left_anti")
save("orders", orders)

valid_orders = orders.select("order_id").distinct()
valid_products = products.select("product_id").distinct()

items = (
    latest(get("order_items"), "order_item_id")
    .withColumn("quantity", F.expr("try_cast(quantity as int)"))
    .withColumn("unit_price_usd", money("unit_price_usd"))
    .withColumn("discount_pct", F.expr("try_cast(discount_pct as double)"))
    .withColumn("line_total_usd", money("line_total_usd"))
)
items_ok = items.join(valid_orders, "order_id", "inner").join(valid_products, "product_id", "inner")
save("rejected_order_items", items.join(items_ok.select("order_item_id"), "order_item_id", "left_anti"))
save("order_items", items_ok)

payments = (
    latest(get("payments"), "payment_id")
    .withColumn("payment_datetime", timestamp("payment_datetime"))
    .withColumn("payment_status", F.lower(F.trim("payment_status")))
    .withColumn("amount_usd", money("amount_usd"))
    .withColumn("currency", F.upper(F.trim("currency")))
)
payments_ok = payments.join(valid_orders, "order_id", "inner")
save("rejected_payments", payments.join(payments_ok.select("payment_id"), "payment_id", "left_anti"))
save("payments", payments_ok)

# COMMAND ----------
events = (
    latest(get("website_events"), "event_id")
    .withColumn("event_datetime", timestamp("event_datetime"))
    .withColumn("event_type", F.lower(F.trim("event_type")))
    .withColumn("product_id", F.when(F.trim("product_id") == "", None).otherwise(F.col("product_id")))
    .withColumn("order_id", F.when(F.trim("order_id") == "", None).otherwise(F.col("order_id")))
)
valid_sessions = sessions.select("session_id").distinct()
events_ok = events.join(valid_sessions, "session_id", "inner")
# Product can be optional for generic events, but non-empty IDs must resolve to product dimension.
events_ok = events_ok.join(valid_products.withColumn("_product_exists", F.lit(True)), "product_id", "left")
events_ok = events_ok.filter(F.col("product_id").isNull() | F.col("_product_exists")).drop("_product_exists")
save("rejected_website_events", events.join(events_ok.select("event_id"), "event_id", "left_anti"))
save("website_events", events_ok)

# Small JSON lookup tables are part of the source package.
for name in ("marketing_campaigns", "shipping_methods"):
    original = get(name)
    key = "campaign_id" if name == "marketing_campaigns" else "shipping_method"
    save(name, latest(original, key))

print("Silver complete. All rejections are available in silver_rejected_* tables.")
