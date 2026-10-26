# Databricks notebook source
# NovaCart PoC | 03: Build BI-ready Gold facts, dimensions and monthly marts.

# COMMAND ----------
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "novacart_poc", "Target schema")

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()


def ident(value):
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"Invalid identifier: {value!r}")
    return f"`{value}`"


PREFIX = f"{ident(CATALOG)}.{ident(SCHEMA)}"


def silver(name):
    return spark.table(f"{PREFIX}.{ident('silver_' + name)}")


def write_gold(name, df):
    table_name = f"{PREFIX}.{ident('gold_' + name)}"
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)
    print("Gold saved:", table_name, df.count(), "rows")


spark.conf.set("spark.sql.session.timeZone", "UTC")
Z = F.lit(0).cast("decimal(18,2)")

# COMMAND ----------
customers = silver("customers")
products = silver("products")
orders = silver("orders")
items = silver("order_items")
payments = silver("payments")
sessions = silver("website_sessions")
events = silver("website_events")

write_gold("dim_customers", customers.select("customer_id", "signup_date", "country_code", "country", "city", "customer_tier", "signup_channel"))
write_gold("dim_products", products.select("product_id", "product_name", "category", "list_price_usd", "unit_cost_usd", "product_status"))
write_gold("dim_campaigns", silver("marketing_campaigns"))

# Payment-grain measures: captured positive; refunds negative; failed excluded.
write_gold("fact_payments", payments.select("payment_id", "order_id", "payment_datetime", "payment_status", "payment_method", "amount_usd", "currency"))
payment_by_order = payments.groupBy("order_id").agg(
    F.sum(F.when(F.col("payment_status") == "captured", F.col("amount_usd")).otherwise(Z)).alias("captured_amount_usd"),
    F.sum(F.when(F.col("payment_status") == "refunded", F.col("amount_usd")).otherwise(Z)).alias("refunded_amount_usd"),
)

# Grain: one order. Never directly join multiple payments to multiple order items.
fact_orders = (
    orders.join(payment_by_order, "order_id", "left")
    .withColumn("captured_amount_usd", F.coalesce("captured_amount_usd", Z))
    .withColumn("refunded_amount_usd", F.coalesce("refunded_amount_usd", Z))
    .withColumn("net_revenue_usd", F.col("captured_amount_usd") - F.col("refunded_amount_usd"))
    .withColumn("is_paid_order", (F.col("order_status") == "paid") & (F.col("captured_amount_usd") > 0))
    .withColumn("order_date", F.to_date("order_datetime"))
    .withColumn("order_month", F.date_format("order_datetime", "yyyy-MM"))
)
write_gold("fact_orders", fact_orders.select(
    "order_id", "customer_id", "session_id", "order_datetime", "order_date", "order_month", "record_month",
    "order_status", "is_paid_order", "sales_channel", "country_code", "campaign_id", "currency",
    "order_total_usd", "captured_amount_usd", "refunded_amount_usd", "net_revenue_usd",
))

# Grain: one order item. Allocate order-level net receipts proportionally for category/product charts.
# Keep unrounded decimal allocation; Power BI can round displayed totals.
item_facts = (
    items.join(fact_orders.select("order_id", "order_date", "order_month", "customer_id", "sales_channel", "order_status", "order_total_usd", "net_revenue_usd"), "order_id", "inner")
    .join(products.select("product_id", "product_name", "category", "unit_cost_usd"), "product_id", "inner")
    .withColumn("allocated_net_revenue_usd", F.when(F.col("order_total_usd") > 0,
        F.col("net_revenue_usd") * F.col("line_total_usd") / F.col("order_total_usd"))
        .otherwise(F.lit(0)))
    .withColumn("estimated_item_cost_usd", F.col("unit_cost_usd") * F.col("quantity"))
)
write_gold("fact_order_items", item_facts.select(
    "order_item_id", "order_id", "product_id", "product_name", "category", "customer_id", "order_date",
    "order_month", "sales_channel", "order_status", "quantity", "unit_price_usd", "discount_pct",
    "line_total_usd", "allocated_net_revenue_usd", "estimated_item_cost_usd",
))

write_gold("fact_sessions", sessions.select("session_id", "session_start", "record_month", "customer_id", "country_code", "sales_channel", "device_type", "campaign_id", "order_id"))
write_gold("fact_website_events", events.select("event_id", "session_id", "event_datetime", "event_type", "product_id", "order_id", "record_month"))

# COMMAND ----------
monthly_sales = fact_orders.groupBy("order_month", "sales_channel").agg(
    F.sum("net_revenue_usd").alias("net_revenue_usd"),
    F.sum("captured_amount_usd").alias("captured_usd"),
    F.sum("refunded_amount_usd").alias("refunded_usd"),
    F.count("order_id").alias("orders_total"),
    F.sum(F.col("is_paid_order").cast("int")).alias("paid_orders"),
    F.sum(F.when(F.col("order_status") == "cancelled", 1).otherwise(0)).alias("cancelled_orders"),
    F.sum(F.when(F.col("order_status") == "returned", 1).otherwise(0)).alias("returned_orders"),
)
write_gold("sales_monthly", monthly_sales)

product_monthly = item_facts.groupBy("order_month", "category", "product_id", "product_name", "sales_channel").agg(
    F.sum("quantity").alias("units_sold"),
    F.countDistinct("order_id").alias("order_count"),
    F.sum("allocated_net_revenue_usd").alias("allocated_net_revenue_usd"),
    F.sum("estimated_item_cost_usd").alias("estimated_cost_usd"),
)
write_gold("product_monthly", product_monthly)

customer_summary = fact_orders.groupBy("customer_id").agg(
    F.count("order_id").alias("total_orders"),
    F.sum(F.col("is_paid_order").cast("int")).alias("paid_order_count"),
    F.min("order_date").alias("first_order_date"),
    F.max("order_date").alias("last_order_date"),
    F.sum("net_revenue_usd").alias("lifetime_net_revenue_usd"),
)
write_gold("customer_summary", customer_summary)

# One session is the conversion denominator; multiple events in a session must not multiply it.
visitor_sessions = sessions.groupBy("record_month", "sales_channel").agg(F.countDistinct("session_id").alias("sessions"))
converted_sessions = sessions.filter(F.col("order_id").isNotNull()).groupBy("record_month", "sales_channel").agg(F.countDistinct("session_id").alias("sessions_with_order"))
funnel = visitor_sessions.join(converted_sessions, ["record_month", "sales_channel"], "left").fillna({"sessions_with_order": 0})
write_gold("website_funnel_monthly", funnel.withColumn("conversion_rate", F.when(F.col("sessions") > 0, F.col("sessions_with_order") / F.col("sessions")).otherwise(F.lit(0))))

print("Gold complete. Run 04_validate_quality.py before connecting Power BI.")
