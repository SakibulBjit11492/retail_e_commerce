# Architecture — NOVACART_MINI_V2

Synthetic CSV / JSON (USD, Jan–Dec 2025; Japan + ASEAN)
  -> **Azure Data Lake Storage Gen2**
  -> **Unity Catalog external volume** (`/Volumes/.../raw/`)
  -> **Databricks Bronze** (append-only raw Delta tables + ingestion audit columns)
  -> **Databricks Silver** (standardization, deduplication, orphan rejection, repair)
  -> **Databricks Gold** (dimensions, facts, monthly marts)
  -> **Power BI** (3 mandatory dashboard reports)

Additional dashboards (marketing, operations, executive) can follow when datasets expand.

## Key operational decisions

- **Ingestion:** Databricks notebooks run after files are uploaded; scheduled Databricks job preferred for PoC over always-on services. Azure Data Factory remains optional.
- **Storage access:** Use Unity Catalog storage credential + external location + external volume managed by the Azure workspace admins. No access keys hardcoded.
- **Bronze:** append-only; repeated reads create additional raw records with new `_ingested_at_utc` / `_load_batch_id`.
- **Silver:** distinct business keys and overwrite small validated Delta tables. Production scalability could replace these small-table overwrites with `MERGE`.
- **Gold:** full deterministic rebuild from Silver (idempotent, one fact grain per table).
- **Reconciliation:** Revenue in this demo means **net captured payment amount less refunds**, not accounting accrual revenue. Failed payments count as zero. Paid order is `order_status='paid'` with captured payment.
- **Cost:** choose serverless only for manual testing, pause SQL warehouses and avoid unnecessary background workloads. Serverless usage is billable, even if there is no active classic cluster.

## Gold table grains

| Table | Grain |
|---|---|
| `gold_dim_customers` | 1/customer |
| `gold_dim_products` | 1/product |
| `gold_fact_orders` | 1/order |
| `gold_fact_order_items` | 1/order item |
| `gold_fact_payments` | 1/payment transaction |
| `gold_fact_sessions` | 1/web or app session |
| `gold_fact_website_events` | 1/event |
| `gold_sales_monthly` | month × sales channel |
| `gold_product_monthly` | month × category × product × channel |
| `gold_customer_summary` | 1/customer |
| `gold_website_funnel_monthly` | month × sales channel |

## Demo measurements

- Total net revenue: `SUM(gold_fact_orders.net_revenue_usd)`
- Paid orders: `COUNT` where `is_paid_order=true`
- Average order value: captured amount divided by number of paid orders (state this definition in BI)
- Return rate: returned order count / all orders (chosen denominator must be documented)
- Cancellation rate: cancelled orders / all orders
- Session-to-order conversion: sessions with linked order / all sessions

**Important:** `gold_product_monthly.allocated_net_revenue_usd` is allocated proportionally from order-level payment net; do **not** join payment rows directly to product rows because that inflates sums.

## Next enhancements

- Add marketing spend for ROAS and more detailed shipment/return data for delivery KPIs.
- Add separate rejection reasons, freshness checks, alerting, CI/CD, and incremental MERGE workflows.
