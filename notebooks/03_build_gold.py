# Databricks notebook source
# NovaCart PoC | 03: Build BI-ready Gold star schema (dimensions, facts) and monthly marts.
# Full deterministic rebuild from Silver on every run (idempotent).

# COMMAND ----------
dbutils.widgets.text("catalog", "dpe_azure_poc", "Unity Catalog catalog")
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
    print("Gold saved:", table_name, spark.table(table_name).count(), "rows")


spark.conf.set("spark.sql.session.timeZone", "UTC")
Z = F.lit(0).cast("decimal(18,2)")

customers = silver("customers")
products = silver("products")
orders = silver("orders")
items = silver("order_items")
payments = silver("payments")
sessions = silver("website_sessions")
events = silver("website_events")

# COMMAND ----------
# MAGIC %md ## Dimensions

# COMMAND ----------
write_gold("dim_customers", customers.select(
    "customer_id", "customer_label", "signup_date", "country_code", "country", "city", "customer_tier", "signup_channel"))
write_gold("dim_products", products.select(
    "product_id", "product_name", "category", "list_price_usd", "unit_cost_usd", "product_status"))

# Campaigns + the two non-campaign codes used by orders/sessions, so every campaign_id has a dimension row.
campaign_cols = ["campaign_id", "campaign_name", "marketing_source", "campaign_objective", "channel"]
no_campaign = spark.createDataFrame(
    [("ORGANIC", "Organic (no campaign)", "organic", "none", "all"),
     ("DIRECT", "Direct (no campaign)", "direct", "none", "all")], campaign_cols)
write_gold("dim_campaigns", silver("marketing_campaigns").select(*campaign_cols).unionByName(no_campaign)
           .withColumn("is_paid_campaign", ~F.col("campaign_id").isin("ORGANIC", "DIRECT")))

# One shared channel slicer for orders and sessions. Marketplace orders have no website sessions.
channels = orders.select("sales_channel").union(sessions.select("sales_channel")).distinct()
write_gold("dim_channel", channels.select(
    "sales_channel",
    F.when(F.col("sales_channel") == "web", "Web shop")
     .when(F.col("sales_channel") == "mobile_app", "Mobile app")
     .when(F.col("sales_channel") == "marketplace", "Marketplace")
     .otherwise(F.initcap(F.regexp_replace("sales_channel", "_", " "))).alias("channel_name"),
    (F.col("sales_channel") != "marketplace").alias("has_web_sessions"),
))

# Calendar covering full years of all order/session/payment dates (needed for trends and period-over-period).
bounds = (orders.select(F.to_date("order_datetime").alias("d"))
          .union(sessions.select(F.to_date("session_start")))
          .union(payments.select(F.to_date("payment_datetime")))
          .agg(F.min("d").alias("lo"), F.max("d").alias("hi")).first())
dim_date = (
    spark.range(1)
    .select(F.explode(F.sequence(F.trunc(F.lit(bounds["lo"]), "year"),
                                 F.date_sub(F.add_months(F.trunc(F.lit(bounds["hi"]), "year"), 12), 1))).alias("date"))
    .select(
        "date",
        F.date_format("date", "yyyyMMdd").cast("int").alias("date_key"),
        F.year("date").alias("year"),
        F.quarter("date").alias("quarter"),
        F.concat(F.year("date"), F.lit("-Q"), F.quarter("date")).alias("year_quarter"),
        F.month("date").alias("month_num"),
        F.date_format("date", "MMMM").alias("month_name"),
        F.date_format("date", "MMM").alias("month_short"),
        F.date_format("date", "yyyy-MM").alias("year_month"),
        F.trunc("date", "month").alias("month_start"),
        F.date_trunc("week", "date").cast("date").alias("week_start"),  # Monday
        F.weekofyear("date").alias("iso_week"),
        F.dayofmonth("date").alias("day_of_month"),
        (((F.dayofweek("date") + 5) % 7) + 1).alias("day_of_week_num"),  # Mon=1 ... Sun=7
        F.date_format("date", "EEEE").alias("day_name"),
        F.dayofweek("date").isin(1, 7).alias("is_weekend"),
    )
)
write_gold("dim_date", dim_date)

# COMMAND ----------
# MAGIC %md ## Facts

# COMMAND ----------
# Payment grain. signed_amount_usd: captured +, refunded -, failed 0 (the revenue definition).
fact_payments = payments.select(
    "payment_id", "order_id", "payment_datetime", F.to_date("payment_datetime").alias("payment_date"),
    "payment_status", "payment_method", "amount_usd", "currency",
    F.when(F.col("payment_status") == "captured", F.col("amount_usd"))
     .when(F.col("payment_status") == "refunded", -F.col("amount_usd"))
     .otherwise(Z).cast("decimal(18,2)").alias("signed_amount_usd"),
)
write_gold("fact_payments", fact_payments)

payment_by_order = payments.groupBy("order_id").agg(
    F.sum(F.when(F.col("payment_status") == "captured", F.col("amount_usd")).otherwise(Z)).alias("captured_amount_usd"),
    F.sum(F.when(F.col("payment_status") == "refunded", F.col("amount_usd")).otherwise(Z)).alias("refunded_amount_usd"),
)

# Order grain. Never directly join multiple payments to multiple order items.
fact_orders = (
    orders.join(payment_by_order, "order_id", "left")
    .withColumn("captured_amount_usd", F.coalesce("captured_amount_usd", Z))
    .withColumn("refunded_amount_usd", F.coalesce("refunded_amount_usd", Z))
    .withColumn("net_revenue_usd", F.col("captured_amount_usd") - F.col("refunded_amount_usd"))
    .withColumn("is_paid_order", (F.col("order_status") == "paid") & (F.col("captured_amount_usd") > 0))
    .withColumn("order_date", F.to_date("order_datetime"))
    .withColumn("order_month", F.date_format("order_datetime", "yyyy-MM"))
)
# New vs returning: a customer's first *paid* order is "New"; later paid orders are "Returning".
paid_seq = Window.partitionBy("customer_id").orderBy("order_datetime", "order_id")
paid_rank = (fact_orders.filter("is_paid_order")
             .select("order_id", F.row_number().over(paid_seq).alias("paid_order_seq")))
fact_orders = (
    fact_orders.join(paid_rank, "order_id", "left")
    .withColumn("is_first_paid_order", F.coalesce(F.col("paid_order_seq") == 1, F.lit(False)))
    .withColumn("customer_type", F.when(F.col("paid_order_seq") == 1, "New")
                                  .when(F.col("paid_order_seq") > 1, "Returning"))
)
write_gold("fact_orders", fact_orders.select(
    "order_id", "customer_id", "session_id", "order_datetime", "order_date", "order_month", "record_month",
    "order_status", "is_paid_order", "paid_order_seq", "is_first_paid_order", "customer_type",
    "sales_channel", "country_code", "campaign_id", "currency",
    "order_total_usd", "captured_amount_usd", "refunded_amount_usd", "net_revenue_usd",
))

# Order-item grain. Order-level net receipts are allocated to lines by line value, so revenue can be
# filtered by product/category and still sums back to fact_orders (checked in 04_validate_quality).
item_facts = (
    items.join(fact_orders.select("order_id", "order_date", "order_month", "customer_id", "sales_channel",
                                  "country_code", "campaign_id", "order_status", "is_paid_order", "customer_type",
                                  "order_total_usd", "net_revenue_usd"), "order_id", "inner")
    .join(products.select("product_id", "product_name", "category", "unit_cost_usd"), "product_id", "inner")
    .withColumn("allocated_net_revenue_usd", F.when(
        F.col("order_total_usd") > 0,
        F.col("net_revenue_usd") * F.col("line_total_usd") / F.col("order_total_usd")).otherwise(F.lit(0)))
    .withColumn("estimated_item_cost_usd", F.col("unit_cost_usd") * F.col("quantity"))
)
write_gold("fact_order_items", item_facts.select(
    "order_item_id", "order_id", "product_id", "product_name", "category", "customer_id", "order_date",
    "order_month", "sales_channel", "country_code", "campaign_id", "order_status", "is_paid_order",
    "customer_type", "quantity", "unit_price_usd", "discount_pct", "line_total_usd",
    "allocated_net_revenue_usd", "estimated_item_cost_usd",
))

write_gold("fact_sessions", sessions.select(
    "session_id", "session_start", F.to_date("session_start").alias("session_date"), "record_month",
    "customer_id", "country_code", "sales_channel", "device_type", "campaign_id", "order_id",
    F.col("order_id").isNotNull().alias("has_order"),
))
write_gold("fact_website_events", events.select(
    "event_id", "session_id", "event_datetime", F.to_date("event_datetime").alias("event_date"),
    "event_type", "product_id", "order_id", "record_month",
))

# COMMAND ----------
# MAGIC %md ## Marts

# COMMAND ----------
monthly_sales = fact_orders.groupBy("order_month", "sales_channel").agg(
    F.sum("net_revenue_usd").alias("net_revenue_usd"),
    F.sum("captured_amount_usd").alias("captured_usd"),
    F.sum("refunded_amount_usd").alias("refunded_usd"),
    F.count("order_id").alias("orders_total"),
    F.sum(F.col("is_paid_order").cast("int")).alias("paid_orders"),
    F.sum(F.when(F.col("order_status") == "cancelled", 1).otherwise(0)).alias("cancelled_orders"),
    F.sum(F.when(F.col("order_status") == "returned", 1).otherwise(0)).alias("returned_orders"),
    F.sum(F.col("is_first_paid_order").cast("int")).alias("new_customer_orders"),
)
write_gold("sales_monthly", monthly_sales)

product_monthly = item_facts.groupBy("order_month", "category", "product_id", "product_name", "sales_channel").agg(
    F.sum("quantity").alias("units_sold"),
    F.countDistinct("order_id").alias("order_count"),
    F.sum("allocated_net_revenue_usd").alias("allocated_net_revenue_usd"),
    F.sum("estimated_item_cost_usd").alias("estimated_cost_usd"),
    F.countDistinct(F.when(F.col("order_status") == "returned", F.col("order_id"))).alias("returned_order_count"),
    F.countDistinct(F.when(F.col("order_status") == "cancelled", F.col("order_id"))).alias("cancelled_order_count"),
)
write_gold("product_monthly", product_monthly)

# COMMAND ----------
# Customer summary with RFM segmentation (one row per customer, including customers with no orders).
# Recency is measured against the latest order date in the data (not today), so results are reproducible.
as_of_date = fact_orders.agg(F.max("order_date")).first()[0]
order_stats = fact_orders.groupBy("customer_id").agg(
    F.count("order_id").alias("total_orders"),
    F.sum(F.col("is_paid_order").cast("int")).alias("paid_order_count"),
    F.sum(F.when(F.col("order_status") == "cancelled", 1).otherwise(0)).alias("cancelled_order_count"),
    F.sum(F.when(F.col("order_status") == "returned", 1).otherwise(0)).alias("returned_order_count"),
    F.min("order_date").alias("first_order_date"),
    F.max("order_date").alias("last_order_date"),
    F.min(F.when(F.col("is_paid_order"), F.col("order_date"))).alias("first_paid_order_date"),
    F.max(F.when(F.col("is_paid_order"), F.col("order_date"))).alias("last_paid_order_date"),
    F.sum("net_revenue_usd").alias("lifetime_net_revenue_usd"),
)
summary = (
    customers.select("customer_id", "signup_date", "country_code", "customer_tier", "signup_channel")
    .join(order_stats, "customer_id", "left")
    .fillna(0, ["total_orders", "paid_order_count", "cancelled_order_count", "returned_order_count"])
    .withColumn("lifetime_net_revenue_usd", F.coalesce("lifetime_net_revenue_usd", Z))
    .withColumn("as_of_date", F.lit(as_of_date))
    .withColumn("recency_days", F.datediff("as_of_date", "last_paid_order_date"))
)
buyers = summary.filter("paid_order_count > 0")
r_win = Window.orderBy(F.col("recency_days").desc(), "customer_id")          # most recent -> 5
m_win = Window.orderBy(F.col("lifetime_net_revenue_usd").asc(), "customer_id")  # highest value -> 5
scores = buyers.select(
    "customer_id",
    F.ntile(5).over(r_win).alias("r_score"),
    F.least(F.col("paid_order_count"), F.lit(5)).cast("int").alias("f_score"),  # 1..5+ paid orders
    F.ntile(5).over(m_win).alias("m_score"),
)
r, f, m = F.col("r_score"), F.col("f_score"), F.col("m_score")
customer_summary = (
    summary.join(scores, "customer_id", "left")
    .withColumn("rfm_score", F.when(r.isNotNull(), F.concat(r.cast("string"), f.cast("string"), m.cast("string"))))
    .withColumn("rfm_segment",
                F.when(r.isNull(), "No purchase")
                 .when((r >= 4) & (f >= 2), "Champions")
                 .when((r >= 3) & (f >= 2), "Loyal")
                 .when(f >= 2, "At risk")
                 .when((r >= 4) & (m >= 4), "Promising")
                 .when(r >= 4, "New")
                 .when(r == 3, "Needs attention")
                 .otherwise("Hibernating"))
    .withColumn("buyer_type", F.when(F.col("paid_order_count") >= 2, "Repeat")
                               .when(F.col("paid_order_count") == 1, "One-time")
                               .otherwise("No purchase"))
    .withColumn("avg_paid_order_value_usd", F.when(
        F.col("paid_order_count") > 0, F.col("lifetime_net_revenue_usd") / F.col("paid_order_count")))
)
write_gold("customer_summary", customer_summary)

# COMMAND ----------
# One session is the conversion denominator; multiple events in a session must not multiply it.
visitor_sessions = sessions.groupBy("record_month", "sales_channel").agg(F.countDistinct("session_id").alias("sessions"))
converted_sessions = (sessions.filter(F.col("order_id").isNotNull()).groupBy("record_month", "sales_channel")
                      .agg(F.countDistinct("session_id").alias("sessions_with_order")))
funnel = visitor_sessions.join(converted_sessions, ["record_month", "sales_channel"], "left").fillna({"sessions_with_order": 0})
write_gold("website_funnel_monthly", funnel.withColumn(
    "conversion_rate", F.when(F.col("sessions") > 0, F.col("sessions_with_order") / F.col("sessions")).otherwise(F.lit(0))))

print("Gold complete. Run 04_validate_quality before connecting Power BI.")
