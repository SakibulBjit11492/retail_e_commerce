# Databricks notebook source
# NovaCart PoC | 04: Automated per-load Data Quality gate and revenue reconciliation.

# COMMAND ----------
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Target schema")
dbutils.widgets.text("revenue_tolerance_usd", "0.01", "Allowed absolute difference, USD")

# COMMAND ----------
from decimal import Decimal
from pyspark.sql import functions as F

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
TOLERANCE = Decimal(dbutils.widgets.get("revenue_tolerance_usd"))


def ident(s):
    if not s or not s.replace("_", "").isalnum():
        raise ValueError(f"Invalid identifier: {s!r}")
    return f"`{s}`"


PREFIX = f"{ident(CATALOG)}.{ident(SCHEMA)}"


def table(layer, name):
    return spark.table(f"{PREFIX}.{ident(layer + '_' + name)}")


results = []


def check(name, passed, details):
    results.append((name, "PASS" if passed else "FAIL", str(details)))
    print(("PASS" if passed else "FAIL"), name, details)


# COMMAND ----------
# Reconcile Bronze to Silver: Bronze may have duplicate loads and known quarantined records.
keys = {
    "customers": "customer_id", "products": "product_id", "orders": "order_id",
    "order_items": "order_item_id", "payments": "payment_id",
    "website_sessions": "session_id", "website_events": "event_id",
}
for name, key in keys.items():
    b = table("bronze", name)
    s = table("silver", name)
    bronze_total = b.count()
    silver_total = s.count()
    unique_bronze = b.select(key).distinct().count()
    reject_name = {
        "orders": "rejected_orders", "order_items": "rejected_order_items",
        "payments": "rejected_payments", "website_events": "rejected_website_events",
    }.get(name)
    rejected = table("silver", reject_name).count() if reject_name else 0
    check(f"bronze_silver_row_count_{name}", bronze_total >= unique_bronze and unique_bronze == silver_total + rejected,
          f"bronze={bronze_total}; unique_raw={unique_bronze}; silver={silver_total}; rejected={rejected}; duplicate_reloads={bronze_total-unique_bronze}")

# Gold null and orphan foreign keys at fact grain.
orders = table("gold", "fact_orders")
items = table("gold", "fact_order_items")
products = table("gold", "dim_products")
customers = table("gold", "dim_customers")
payments = table("gold", "fact_payments")

for name, df, field in [
    ("orders", orders, "order_id"), ("orders_customers", orders, "customer_id"),
    ("items", items, "order_item_id"), ("items_orders", items, "order_id"),
    ("items_products", items, "product_id"), ("payments", payments, "payment_id"),
    ("payments_orders", payments, "order_id"),
]:
    invalid = df.filter(F.col(field).isNull() | (F.trim(F.col(field)) == "")).count()
    check(f"gold_required_key_{name}", invalid == 0, f"null_or_empty={invalid}")

for name, source_df, target_df, fk in [
    ("order_customer", orders, customers, "customer_id"),
    ("item_order", items, orders, "order_id"),
    ("item_product", items, products, "product_id"),
    ("payment_order", payments, orders, "order_id"),
]:
    count = source_df.select(fk).join(target_df.select(fk).distinct(), fk, "left_anti").count()
    check(f"gold_orphan_{name}", count == 0, f"orphan_rows={count}")

for name, df, key in [
    ("fact_orders", orders, "order_id"),
    ("fact_order_items", items, "order_item_id"),
    ("fact_payments", payments, "payment_id"),
    ("fact_sessions", table("gold", "fact_sessions"), "session_id"),
]:
    total = df.count()
    uniq = df.select(key).distinct().count()
    check(f"gold_unique_{name}", total == uniq, f"rows={total}; distinct_{key}={uniq}")

# Reconcile payment-level captured minus refunded directly against order-level net receipts.
source_row = payments.agg(F.sum(F.when(F.col("payment_status") == "captured", F.col("amount_usd"))
                                    .when(F.col("payment_status") == "refunded", -F.col("amount_usd"))
                                    .otherwise(0)).alias("amount")).first()
target_row = orders.agg(F.sum("net_revenue_usd").alias("amount")).first()
source_usd = Decimal(str(source_row["amount"] or 0))
target_usd = Decimal(str(target_row["amount"] or 0))
delta = abs(source_usd - target_usd)
check("revenue_reconciles_to_payments", delta <= TOLERANCE,
      f"payment_net={source_usd}; gold_net={target_usd}; delta={delta}; tolerance={TOLERANCE}")

# COMMAND ----------
from datetime import datetime, timezone
stamp = datetime.now(timezone.utc)
rows = [(stamp, x[0], x[1], x[2]) for x in results]
report = spark.createDataFrame(rows, "check_ts timestamp, check_name string, status string, details string")
report.write.format("delta").mode("append").saveAsTable(f"{PREFIX}.`dq_results`")
failures = [x for x in results if x[1] == "FAIL"]
print(f"Data quality: {len(results) - len(failures)}/{len(results)} checks passed.")
if failures:
    raise RuntimeError("Data quality gate failed: " + ", ".join(x[0] for x in failures))
