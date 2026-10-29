# NovaCart live demo runbook (15 minutes)

For a salesperson presenting, with an engineer on call. Every step lists what to click and what the screen must show.
If any step fails or hangs for more than 60 seconds: say "let me show you the recorded run", play the 3-minute customer video, and continue the conversation. Do not troubleshoot live.

## Roles and access

| Who | Needs |
|---|---|
| Presenter (Sales) | Power BI workspace `dpe-azure-poc` (Viewer), Databricks workspace (job **Can Manage Run**) |
| Engineer on call | Databricks admin on `dpe_azure_poc`, Azure portal, this repo |

## One-time setup (engineer)

1. Deploy jobs: Databricks Git folder → **Pull** → `databricks.yml` → Deployments → target **prod** → **Deploy**. This creates three jobs: `novacart-medallion-pipeline`, `novacart-demo-drop-month`, `novacart-demo-reset`.
2. Stage the demo month: upload the 6 CSVs from `data/demo_batch_2026_01/` to the volume folder `demo_staging/2026_01/` (Catalog → `dpe_azure_poc` → `novacart_poc` → volume `landing`), or run `bash infra/01_azure_setup.sh`.
3. Run `novacart-demo-reset` once and check that the last task ends with `32/32 checks passed`.
4. Power BI: dashboard tile refresh set to the longest interval; present the report in **Reading view**, full screen (no trial banner, no account menu visible).

## Before the meeting (T-10 min, presenter or engineer)

| # | Action | Check |
|---|---|---|
| 1 | Databricks → **Jobs & Pipelines** → `novacart-demo-reset` → **Run now** (≈ 4 min) | All tasks green; last task prints `32/32 checks passed` |
| 2 | T-5 min: **SQL Warehouses** → `wh-novacart-bi` → **Start** | Status **Running** |
| 3 | Power BI → `NovaCart PoC Report` → **Refresh** → **Reading view** → full screen | Net Revenue **40.06K**, Paid Orders **1.25K**, AOV **32.05**; last month on the chart **2025-12** |
| 4 | Open three browser tabs: Power BI report · job `novacart-demo-drop-month` · job `novacart-medallion-pipeline` | Tabs ready, nothing else open; notifications off |
| 5 | Have the 3-minute customer video open in a fourth tab | Plays offline |

## Live script (15 minutes)

| Time | Say (short) | Do | Screen must show |
|---|---|---|---|
| 0:00–2:00 | "Most retailers stitch four systems together in Excel every month. Here is the same business with one trusted view." | Power BI tab | 40.06K net revenue · 1.25K paid orders · 32.05 average order · line rising sharply in Nov–Dec |
| 2:00–4:00 | "Which products sell, and which come back?" | Point at **Revenue by Category** and **Order Status** | Travel & Bags 6.1K on top · 9.38% cancelled · 3.82% returned |
| 4:00–5:30 | "Who buys, and how many visitors buy?" | Point at **Website Activity** and **Revenue by Channel** | Funnel ends at 11.6% · marketplace 43.51% |
| 5:30–6:30 | "Now a new month of sales arrives from the shop systems." | Tab 2: `novacart-demo-drop-month` → **Run now** (≈ 1 min) | Run succeeded · output lists 6 `*_2026_01_USD.csv` files |
| 6:30–11:30 | "One job cleans, combines and checks everything. No manual steps." | Tab 3: `novacart-medallion-pipeline` → **Run now** → open the run → **Graph**; talk while the 5 boxes turn green (≈ 5 min) | `ingest_bronze`: 6 files appended, 2025 files skipped |
| 11:30–13:00 | "Before anything reaches a dashboard, 32 checks confirm nothing is missing or doubled and revenue matches payments to the cent." | Click the `validate_quality` box → output | `Data quality: 32/32 checks passed.` |
| 13:00–14:30 | "And the dashboards already show January." | Power BI tab → **Refresh** | Chart ends at **2026-01** · Net Revenue **41.19K** · Paid Orders **1.28K** |
| 14:30–15:00 | "This runs for about a dollar of cloud compute. We can do the same on your data in a 2-week PoC." | — | — |

## Expected numbers (one source: `case-study/numbers_sheet.csv`)

| Measure | Before January | After January |
|---|---:|---:|
| Net revenue | $40,058.06 (card 40.06K) | $41,194.74 (card 41.19K) |
| Orders (all) | 1,440 | 1,480 |
| Paid orders | 1,250 | 1,283 |
| January 2026 net revenue | — | $1,164.93 |
| Average order value | $32.05 | ≈ $32.1 |
| Last month on revenue chart | 2025-12 | 2026-01 |
| Quality checks | 32/32 | 32/32 |
| Rejected website events | 3 | 4 |
| Order `ORD0031997` (Dec 2025) | paid | returned, net 0 (late refund in January) |

Numbers come from a full local run of the notebooks (2025 → drop January → reset → drop again). Confirm them once in the workspace after deploying and correct this table if Databricks differs.

## After the meeting

1. `novacart-demo-reset` → **Run now** (restores "before January"; safe to run twice).
2. **SQL Warehouses** → `wh-novacart-bi` → **Stop** (it also stops by itself after 5 minutes idle).

## If something goes wrong

| Symptom | Say / do |
|---|---|
| Any step fails or waits > 60 s | Switch to the 3-minute video without comment; continue the talk track |
| Report shows an error or asks for credentials | Video fallback; engineer: semantic model → Settings → Data source credentials → OAuth2 |
| Pipeline red on `validate_quality` | Video fallback; engineer reads the `FAIL` lines and `dq_results` |
| Report shows 2026-01 before the meeting | Run `novacart-demo-reset` again, then refresh Power BI |

## Demo environment and cost

- Kept **stopped** between demos: jobs run only on request, the SQL warehouse auto-stops after 5 minutes idle, the job schedule is paused.
- One demo session (estimate): reset + drop + pipeline runs on serverless jobs (≈ $1 each) + SQL warehouse ≈ 30 minutes (2X-Small ≈ $1.40) → **about $4–5 per session**. Confirm the per-run figure with the `system.billing.usage` query and update here and in the numbers sheet.
- Whole PoC to date: **$27.35** (23–29 Oct 2026, Azure Cost Management); budget alert $30/month.
