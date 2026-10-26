# Live demo runbook: "drop new raw data, run, dashboards update"

The demo batch `data/demo_batch_2026_01/` is a new month (January 2026) of NovaCart data.
It was generated with `python tools/make_demo_batch.py <dataset folder>` (deterministic, same output every time).

## What the batch contains

| File | Rows |
|---|---:|
| `customers_2026_01_USD.csv` | 12 new customers |
| `orders_2026_01_USD.csv` | 40 new orders + 2 re-sent 2025 orders |
| `order_items_2026_01_USD.csv` | 53 |
| `payments_2026_01_USD.csv` | 42 (includes a late refund) |
| `website_sessions_2026_01_USD.csv` | 83 |
| `website_events_2026_01_USD.csv` | 178 |

Planted problems Silver must handle (details in `manifest.json`):

- status spelled `Completed` → mapped to `paid`
- one `MM/DD/YYYY` order timestamp
- one blank `customer_id`, recovered from the linked session
- one event with product `P_MISSING` → `silver_rejected_website_events`
- `ORD0031451` re-sent unchanged → still one row in Silver
- `ORD0031997` (Dec 2025) re-sent as `returned` with a refund on 2026-01-05 → newer version wins; its net revenue becomes 0

## Before the demo

1. Pipeline has run on the 2025 data only; `04_validate_quality` passes.
2. Power BI is refreshed and the date slicer shows 2025.
3. SQL warehouse is stopped (it starts on refresh).

## Live steps (about 15 minutes)

1. **Drop the data:** Catalog Explorer → volume `landing` → `raw` → upload the 6 CSV files from `data/demo_batch_2026_01/` (not `manifest.json`).
2. **Run:** Workflows → *novacart-medallion-pipeline* → **Run now** (or run notebooks 00–04).
3. **Show Bronze:** the `ingest_bronze` task output lists only the 6 new files as *appended*; the 2025 files are *skipped*.
4. **Show quality:** the `validate_quality` task ends with all checks passed; optionally `SELECT * FROM main.novacart_poc.dq_results ORDER BY check_ts DESC`.
5. **Show the fixes:** `SELECT * FROM main.novacart_poc.silver_rejected_website_events` (4 rows, one new) and
   `SELECT order_id, order_status, net_revenue_usd FROM main.novacart_poc.gold_fact_orders WHERE order_id = 'ORD0031997'`.
6. **Refresh Power BI:** January 2026 appears; revenue, orders and returning customers move.
7. **Idempotency (optional):** run the job again with `force_reload = true`. Bronze grows, but Gold revenue stays the same.

## Expected numbers (from a local simulation of the notebooks)

| Measure | Before (2025 only) | After demo batch |
|---|---:|---:|
| Orders in `gold_fact_orders` | 1,440 | 1,480 |
| Net revenue (USD) | 40,058.06 | 41,194.74 (+1,136.68) |
| Customers | 1,282 | 1,294 |
| Rejected website events | 3 | 4 |

Re-running with no new files, or with `force_reload = true`, leaves these numbers unchanged.
Confirm the "before" numbers in your workspace once and update this table if they differ.
