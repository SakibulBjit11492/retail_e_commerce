# Gold data model and Power BI model

Power BI reads **only** the `gold_*` tables in `<catalog>.<schema>` (default `main.novacart_poc`).
Every Gold table is rebuilt from Silver on each run, so a re-run never double-counts.

## Gold tables

| Table | Grain | Used for |
|---|---|---|
| `gold_dim_date` | 1 row per calendar day (full years covered by the data) | Date slicer, day/week/month trends, period-over-period |
| `gold_dim_channel` | 1 row per sales channel (`web`, `mobile_app`, `marketplace`) | Channel slicer for orders **and** sessions |
| `gold_dim_products` | 1 row per product | Product / category slicer |
| `gold_dim_customers` | 1 row per customer | Country, tier, signup channel |
| `gold_dim_campaigns` | 1 row per campaign, plus `ORGANIC` and `DIRECT` | Campaign attribution (optional) |
| `gold_fact_order_items` | 1 row per order line | **Main sales fact**: revenue, orders, units, returns, cancellations |
| `gold_fact_orders` | 1 row per order | Order-level detail, new vs returning (`customer_type`) |
| `gold_fact_payments` | 1 row per payment transaction | Payment method / status analysis, reconciliation |
| `gold_fact_sessions` | 1 row per website/app session | Session-to-order conversion |
| `gold_fact_website_events` | 1 row per event | Funnel: view → add to cart → checkout → purchase |
| `gold_customer_summary` | 1 row per customer | RFM segments, repeat vs one-time buyers (snapshot, not date-filtered) |
| `gold_sales_monthly`, `gold_product_monthly`, `gold_website_funnel_monthly` | month × channel (× product) | Pre-aggregated marts for quick checks / SQL |

Important columns:

- `gold_fact_order_items.allocated_net_revenue_usd`: the order's net revenue (captured − refunded) split across its lines by line value. Summed over lines it equals `gold_fact_orders.net_revenue_usd` (checked every run). This is what makes **category** filtering of revenue correct.
- `gold_fact_orders.customer_type`: `New` = the customer's first paid order in the data, `Returning` = a later paid order, blank = not a paid order. Copied to `gold_fact_order_items`.
- `gold_fact_sessions.has_order`: the session is linked to an order.
- `gold_customer_summary`: `recency_days` (vs. latest order date in the data), `r_score`, `f_score`, `m_score` (1–5), `rfm_segment`, `buyer_type` (`Repeat`, `One-time`, `No purchase`).

## RFM segmentation rules

Only customers with at least one paid order get scores.

- **R** (recency): quintile of days since the last paid order, 5 = most recent.
- **F** (frequency): number of paid orders, capped at 5 (1, 2, 3, 4, 5+).
- **M** (monetary): quintile of lifetime net revenue, 5 = highest.

| Segment | Rule (checked in this order) |
|---|---|
| Champions | R ≥ 4 and F ≥ 2 |
| Loyal | R ≥ 3 and F ≥ 2 |
| At risk | F ≥ 2 (but R ≤ 2) |
| Promising | F = 1, R ≥ 4, M ≥ 4 |
| New | F = 1, R ≥ 4 |
| Needs attention | F = 1, R = 3 |
| Hibernating | everything else (F = 1, R ≤ 2) |
| No purchase | no paid order |

## Power BI model (star schema)

Load the tables in **Import** mode (cheapest: the SQL warehouse only runs during refresh).
Mark `gold_dim_date` as the date table (`date` column).

Relationships (all single direction, dimension → fact, many-to-one):

| From (fact) | To (dimension) |
|---|---|
| `gold_fact_order_items[order_date]` | `gold_dim_date[date]` |
| `gold_fact_order_items[sales_channel]` | `gold_dim_channel[sales_channel]` |
| `gold_fact_order_items[product_id]` | `gold_dim_products[product_id]` |
| `gold_fact_order_items[customer_id]` | `gold_dim_customers[customer_id]` |
| `gold_fact_orders[order_date]` | `gold_dim_date[date]` |
| `gold_fact_orders[sales_channel]` | `gold_dim_channel[sales_channel]` |
| `gold_fact_orders[customer_id]` | `gold_dim_customers[customer_id]` |
| `gold_fact_orders[campaign_id]` | `gold_dim_campaigns[campaign_id]` |
| `gold_fact_sessions[session_date]` | `gold_dim_date[date]` |
| `gold_fact_sessions[sales_channel]` | `gold_dim_channel[sales_channel]` |
| `gold_fact_website_events[event_date]` | `gold_dim_date[date]` |
| `gold_fact_website_events[product_id]` | `gold_dim_products[product_id]` |
| `gold_fact_payments[payment_date]` | `gold_dim_date[date]` |
| `gold_customer_summary[customer_id]` | `gold_dim_customers[customer_id]` (one-to-one) |

Do **not** relate fact tables to each other (e.g. payments ↔ order items): that multiplies amounts.

### What each slicer filters

| Slicer | Sales & Revenue | Product Performance | Customer Insights |
|---|---|---|---|
| Date (`gold_dim_date`) | ✔ | ✔ | ✔ (except RFM snapshot) |
| Channel (`gold_dim_channel`) | ✔ | ✔ | ✔ |
| Category (`gold_dim_products`) | ✔ (measures use order lines) | ✔ | ✔ for new/returning/frequency; **not** for session conversion (sessions have no category) |

Marketplace orders have no website sessions, so conversion rate is shown for `web` and `mobile_app` only.
