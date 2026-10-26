# NOVACART_MINI_V2 — NovaCart Synthetic Retail Dataset (2025, USD)

**Version tag:** `NOVACART_MINI_V2`. The next larger iteration can be named `NOVACART_MINI_V3` or `NOVACART_FULL_V1`.

## Structure
One file per entity, **no monthly file splitting**. All records are from January–December 2025; use `record_month` (`YYYY-MM`) for monthly grouping.

| File | Rows | Purpose |
| --- | ---: | --- |
| `customers_2025_USD.csv` | 1,282 | Required assignment entity |
| `products_2025_USD.csv` | 400 | Required assignment entity |
| `orders_2025_USD.csv` | 1,446 | Required assignment entity |
| `order_items_2025_USD.csv` | 1,891 | Order-to-product linking for sales analysis |
| `payments_2025_USD.csv` | 1,495 | Required assignment entity |
| `website_sessions_2025_USD.csv` | 6,400 | Required assignment entity |
| `website_events_2025_USD.csv` | 10,644 | Required assignment entity |
| `marketing_campaigns_2025.json` | 12 campaigns | Small optional marketing lookup |
| `shipping_methods_2025.json` | 3 methods | Small optional delivery-method lookup |

## Relationships
- `orders.customer_id` -> `customers.customer_id` (except intentionally missing raw keys)
- `order_items.order_id` -> `orders.order_id`; `order_items.product_id` -> `products.product_id`
- `payments.order_id` -> `orders.order_id`
- `website_events.session_id` -> `website_sessions.session_id`
- `website_sessions.order_id` and purchase `website_events.order_id` -> `orders.order_id`
- `orders.campaign_id` -> `marketing_campaigns.campaign_id` when not `ORGANIC`

## Notes for the assignment
- **Fully synthetic**, no real customer personal data, no brand logos or copyrighted product catalog; generic consumer product names, Japan and ASEAN country/city labels.
- **USD** in all prices and amounts; `2025-01` through `2025-12` supported for time-series visuals.
- **Expected dirty Bronze inputs:** 6 intentionally duplicate order records; 3 orders missing `customer_id`, recoverable by linked session; several non-standard order status/date spellings; 3 view events with deliberately invalid product key `P_MISSING`.
- **Silver:** normalize statuses and timestamps, de-duplicate by `order_id`, repair or quarantine bad keys and orphan events, standardize to UTC; keep track of removed/quarantined records.
- **Gold:** establish order-level and line-level grains before joins; avoid multiplying payment rows due to multi-item orders or refunds.
- **Payment status:** payments are separate transactions. `captured` adds cash, `refunded` subtracts cash, `failed` does not affect net revenue. Reconcile using that definition, and distinguish cash/revenue if your business definition differs.
- **Idempotency:** reloading this dataset should not double-count facts or revenue; use stable IDs and Silver `MERGE`/deduplication as appropriate.
- **Importing the JSON:** `marketing_campaigns_2025.json` and `shipping_methods_2025.json` are distinct lookup entities, not CSV duplicates.
- **Scope:** intentionally compact starter dataset. Returns, shipments, reviews, and full campaign-spend transactions can be added later for richer BI demos.
