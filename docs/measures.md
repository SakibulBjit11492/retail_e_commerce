# Measure definitions (single source of truth)

Every dashboard uses these measures; do not re-create them inside visuals.
Create them in one Power BI table named `_Measures` (Home → Enter data → empty table).
Table names below assume the Gold tables are loaded with their original names.

## Business definitions

| Measure | Business definition |
|---|---|
| **Net Revenue** | Money actually kept: captured payments − refunds. Failed payments count as 0. Cash basis, USD, not accounting accrual revenue. |
| **Paid Order** | An order with status `paid` **and** a captured payment. Cancelled and returned orders are not paid orders. |
| **Paid Orders** | Number of paid orders. |
| **Average Order Value (AOV)** | Net revenue of paid orders ÷ number of paid orders. |
| **Units Sold** | Quantity on paid orders. |
| **Return Rate** | Returned orders ÷ (paid + returned orders), i.e. of the orders that were charged, how many came back. |
| **Cancellation Rate** | Cancelled orders ÷ all orders. |
| **New Customers** | Customers whose first paid order (in the data) falls in the selected period. |
| **Returning Customers** | Customers with a paid order in the period that is not their first paid order. |
| **Purchase Frequency** | Paid orders ÷ buying customers in the period. |
| **Session Conversion Rate** | Sessions linked to an order ÷ all sessions (web + app only; marketplace has no sessions). |
| **MoM %** | (This month − previous month) ÷ previous month, for the measure shown. |

## DAX

```DAX
-- ===== Sales (order-line grain, so category filters work) =====
Net Revenue =
SUM ( gold_fact_order_items[allocated_net_revenue_usd] )

All Orders =
DISTINCTCOUNT ( gold_fact_order_items[order_id] )

Paid Orders =
CALCULATE ( DISTINCTCOUNT ( gold_fact_order_items[order_id] ), gold_fact_order_items[is_paid_order] = TRUE () )

Returned Orders =
CALCULATE ( DISTINCTCOUNT ( gold_fact_order_items[order_id] ), gold_fact_order_items[order_status] = "returned" )

Cancelled Orders =
CALCULATE ( DISTINCTCOUNT ( gold_fact_order_items[order_id] ), gold_fact_order_items[order_status] = "cancelled" )

Average Order Value =
DIVIDE (
    CALCULATE ( [Net Revenue], gold_fact_order_items[is_paid_order] = TRUE () ),
    [Paid Orders]
)

Units Sold =
CALCULATE ( SUM ( gold_fact_order_items[quantity] ), gold_fact_order_items[is_paid_order] = TRUE () )

Return Rate =
DIVIDE ( [Returned Orders], [Paid Orders] + [Returned Orders] )

Cancellation Rate =
DIVIDE ( [Cancelled Orders], [All Orders] )

Estimated Gross Profit =
CALCULATE ( [Net Revenue] - SUM ( gold_fact_order_items[estimated_item_cost_usd] ),
            gold_fact_order_items[is_paid_order] = TRUE () )

-- ===== Period over period (needs gold_dim_date marked as date table) =====
Net Revenue PM =
CALCULATE ( [Net Revenue], DATEADD ( gold_dim_date[date], -1, MONTH ) )

Net Revenue MoM % =
DIVIDE ( [Net Revenue] - [Net Revenue PM], [Net Revenue PM] )

Paid Orders PM =
CALCULATE ( [Paid Orders], DATEADD ( gold_dim_date[date], -1, MONTH ) )

Paid Orders MoM % =
DIVIDE ( [Paid Orders] - [Paid Orders PM], [Paid Orders PM] )

Net Revenue PW =
CALCULATE ( [Net Revenue], DATEADD ( gold_dim_date[date], -7, DAY ) )

Net Revenue WoW % =
DIVIDE ( [Net Revenue] - [Net Revenue PW], [Net Revenue PW] )

-- ===== Customers =====
Buying Customers =
CALCULATE ( DISTINCTCOUNT ( gold_fact_order_items[customer_id] ), gold_fact_order_items[is_paid_order] = TRUE () )

New Customers =
CALCULATE ( DISTINCTCOUNT ( gold_fact_order_items[customer_id] ), gold_fact_order_items[customer_type] = "New" )

Returning Customers =
CALCULATE ( DISTINCTCOUNT ( gold_fact_order_items[customer_id] ), gold_fact_order_items[customer_type] = "Returning" )

Returning Customer % =
DIVIDE ( [Returning Customers], [Buying Customers] )

Purchase Frequency =
DIVIDE ( [Paid Orders], [Buying Customers] )

Customers (RFM) =
COUNTROWS ( gold_customer_summary )

-- ===== Website conversion =====
Sessions =
COUNTROWS ( gold_fact_sessions )

Converted Sessions =
CALCULATE ( COUNTROWS ( gold_fact_sessions ), gold_fact_sessions[has_order] = TRUE () )

Session Conversion Rate =
DIVIDE ( [Converted Sessions], [Sessions] )

Funnel Sessions =   -- use with gold_fact_website_events[event_type] on the axis
DISTINCTCOUNT ( gold_fact_website_events[session_id] )
```

Formatting: currency measures `$#,0.00`; rates and `%` measures as percentage with 1 decimal.

## Suggested visuals

**1. Sales & Revenue:** cards for Net Revenue, Paid Orders, AOV, Net Revenue MoM %; line chart of Net Revenue by `gold_dim_date` hierarchy (year → month → week → day); clustered column of Net Revenue by channel; slicers date, channel, category.

**2. Product Performance:** bar of top 10 products by Net Revenue and by Units Sold; matrix category → product with Net Revenue, Units Sold, Return Rate, Cancellation Rate; scatter Units Sold vs Return Rate by category; same slicers.

**3. Customer Insights:** stacked column New vs Returning Customers by month; cards Purchase Frequency, Returning Customer %, Session Conversion Rate; bar of customers by `rfm_segment`; funnel of Funnel Sessions by event type; same slicers (RFM visuals show the current snapshot).

## Data quality checks (notebook 04, every run)

| Check | Rule |
|---|---|
| `bronze_silver_row_count_*` | Distinct business keys in Bronze = Silver rows + rejected rows (per entity) |
| `gold_required_key_*` | No null/empty keys in Gold facts |
| `gold_orphan_*` | No fact row pointing to a missing customer, order, product or date |
| `gold_unique_*` | No duplicate rows at each fact's grain (and each dimension's key) |
| `revenue_reconciles_to_payments` | Σ Gold net revenue = Σ (captured − refunded) payments, tolerance 0.01 USD |
| `product_allocation_reconciles_to_orders` | Σ allocated line revenue = Σ order net revenue, tolerance 0.01 USD |

Results are appended to `<catalog>.<schema>.dq_results`; any failure stops the job.
