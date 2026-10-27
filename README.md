# NovaCart — Azure Retail & E-commerce Data Platform PoC

**Repository tag:** `NOVACART_POC_CODE_V1`  
**Dataset tag:** `NOVACART_MINI_V2`  
**Business setting:** Fully synthetic, USD, 2025 (+ a January 2026 demo batch), Japan + ASEAN. No real client data and no branded product catalog.

A Git-first PySpark project for Azure Databricks: raw files in ADLS Gen2 are read through a Unity Catalog volume,
processed through Bronze → Silver → Gold Delta tables with a data-quality gate, and served to three Power BI dashboards.

It answers three business questions:

1. **Sales & Revenue:** how much did we really earn, and is it growing?
2. **Product Performance:** which products and categories drive revenue, and which come back or get cancelled?
3. **Customer Insights:** who buys, do they come back, and how many visitors buy?

## Quick start

Follow [`docs/setup.md`](docs/setup.md) (about 1 hour). In short:

1. Resource group `dpe-azure-poc` with tags `project=dpe-azure-poc`, `owner=sakib` and a budget alert.
2. ADLS Gen2 `dpeazurepoc` + Unity Catalog external location and volume `dpe_azure_poc.novacart_poc.landing`.
3. Upload the 9 dataset files to `/Volumes/dpe_azure_poc/novacart_poc/landing/raw/`.
4. Clone this repo as a Databricks Git folder; run notebooks `00` → `04`, or deploy the job with `databricks bundle deploy`.
5. Create the BI views (`sql/novacart_bi_views.sql`), publish `dpe_azure_poc.novacart_bi` to Power BI, and add the measures from [`docs/measures.md`](docs/measures.md).

Live demo steps: [`docs/demo-runbook.md`](docs/demo-runbook.md).

## Naming (use these exact names)

The code, `databricks.yml` and `infra/poc.env` all use these names. The catalog is **`dpe_azure_poc`**, not `main`:
in Power BI's Navigator or Databricks Catalog Explorer, open `dpe_azure_poc` and pick the schema.

| Object | Name |
|---|---|
| Resource group / region | `dpe-azure-poc` / `southeastasia` |
| Storage account (ADLS Gen2) / container | `dpeazurepoc` / `landing` |
| Access connector (managed identity) | `ac-dpe-azure-poc` |
| UC storage credential / external location | `cred_novacart` / `loc_novacart_landing` |
| Catalog | `dpe_azure_poc` |
| Schema, prod (Power BI reads this) | `novacart_poc` |
| Schema, dev (bundle target `dev`) | `novacart_poc_dev` |
| BI schema (Power BI reads only this) | `novacart_bi`: views over Gold, e.g. `novacart_bi.fact_orders` |
| SQL warehouse | `wh-novacart-bi` (serverless 2X-Small, auto-stop 10 min) |
| Power BI workspace / semantic model | `dpe-azure-poc` (Fabric Trial) / `dpe_azure_poc-novacart_bi` |
| Volume / raw folder | `dpe_azure_poc.novacart_poc.landing` → `/Volumes/dpe_azure_poc/novacart_poc/landing/raw/` (ADLS `landing/novacart/raw`) |
| Job | `novacart-medallion-pipeline` (prod), `[dev <user>] novacart-medallion-pipeline` (dev) |
| Tags | `project=dpe-azure-poc`, `owner=sakib` |

## Repository structure

```text
retail_e_commerce/
  README.md
  databricks.yml                     # Databricks Asset Bundle (job deployment)
  resources/
    novacart_pipeline.job.yml        # Job: 00 -> 01 -> 02 -> 03 -> 04 on serverless
  notebooks/
    00_verify_access.py              # checks volume + one file per entity
    01_ingest_bronze.py              # loads only new files; force_reload option
    02_transform_silver.py           # clean, dedupe, repair, quarantine
    03_build_gold.py                 # star schema, RFM, monthly marts
    04_validate_quality.py           # data-quality gate + reconciliation
  data/
    *_2025_USD.csv, *.json           # NOVACART_MINI_V2 (synthetic)
    demo_batch_2026_01/              # new-month batch for the live demo
  docs/
    architecture.md                  # diagram + design decisions
    data-model.md                    # Gold tables, Power BI relationships, RFM rules
    measures.md                      # measure definitions (DAX) + quality checks
    setup.md                         # new-engineer setup
    demo-runbook.md                  # live demo steps and expected numbers
    git-guide.md
  sql/novacart_bi_views.sql          # BI views over Gold (schema novacart_bi)
  powerbi/                           # relationships.tmdl + measures.dax for the semantic model
  tools/
    check_dataset_contract.py        # validate the dataset before upload
    make_demo_batch.py               # regenerate the demo batch
  tests/                             # fast local tests (no Databricks needed)
```

## Run the tests locally

```bash
python -m unittest discover -s tests -v
```

## Notes

- Notebook `.py` files start with `# Databricks notebook source`, so Databricks Git folders open them as notebooks. Catalog, schema and volume are widgets (job parameters when run as a job).
- Serverless compute and SQL warehouses are billable while running. Keep the job schedule paused, use auto-stop, and check Cost Management weekly.
- No secrets in the repo: storage access uses a Unity Catalog credential backed by a managed identity.
- The dataset has no campaign spend or shipment data, so ROAS and delivery SLA metrics are out of scope.
