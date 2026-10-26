# NovaCart — Azure Retail & E-commerce Data Platform PoC

**Repository tag:** `NOVACART_POC_CODE_V1`  
**Dataset tag:** `NOVACART_MINI_V2`  
**Business setting:** Fully synthetic, USD, 2025, Japan + ASEAN. Zero real client data and no branded product catalog.

A compact Git-first PySpark notebook project for Azure Databricks with ADLS Gen2 source files and Unity Catalog-governed Delta tables. Source data is intentionally **not in this code ZIP**. The project is validated statically; Databricks runtime execution remains to be verified after your ADLS/Unity Catalog setup.

## Work sequence

1. **NOW — Git:** Extract ZIP, inspect the notebooks, commit and push the source code. No Azure setup or dataset upload is required for this step.
2. **NEXT — Azure storage:** Create/verify ADLS Gen2; set up the Unity Catalog external location + external volume; upload 7 CSV files + 2 JSON files into `/Volumes/<catalog>/<schema>/<volume>/raw/`.
3. **NEXT — Databricks Git:** Connect supported Git provider and clone the repo as a Git folder; or import these notebook source `.py` files manually if the company Gerrit server isn't supported.
4. **RUN — Databricks:** Open notebook `00_verify_access`, configure widgets to actual catalog/schema/volume, then execute `01_ingest_bronze`, `02_transform_silver`, `03_build_gold`, `04_validate_quality`, in that order. All notebooks run with Databricks serverless when enabled and authorized.
5. **NEXT — Power BI:** Connect to Gold tables and define shared DAX measures. Expand into the other dashboards later.

## Repository structure

```text
novacart-azure-poc/
  README.md
  .gitignore
  .env.example
  notebooks/
    00_verify_access.py
    01_ingest_bronze.py
    02_transform_silver.py
    03_build_gold.py
    04_validate_quality.py
  docs/
    architecture.md
    git-guide.md
  data/
    README.md
  tools/
    check_dataset_contract.py
  tests/
    test_source_schema.py
```

## Notebooks + settings

Notebook source `.py` files start with `# Databricks notebook source`, so Databricks Git folders can recognize them as notebooks. You select the real Unity Catalog catalog, schema, and volume through notebook widgets. The examples use `main` / `novacart_poc` / `landing`, **not guaranteed to exist in your workspace**.

A workspace with Serverless compute **still generates billable usage**. Use a budget alert and review actual cost; do not provision additional clusters just to commit source code.

## Source contract

Inputs are exactly `NOVACART_MINI_V2` files (see `data/README.md`). Both CSV and JSON are consumed in Bronze. `silver_rejected_website_events` captures intentional orphan product references; `silver_rejected_orders` captures unrecoverable broken orders, while recoverable blank customer IDs are repaired through the linked session.

## Reporting model

- **Required:** Sales & Revenue; Product Performance; Customer Insights.
- **Optional after core demo:** Marketing & Conversion; Delivery/Operations (requires additional shipping data); Executive Overview.
- Do not report ROAS without campaign cost data or delivery SLA metrics from lookup-only shipping methods. The starter dataset does not yet include transaction-grain marketing spend or actual shipments.

More information: `docs/architecture.md`, `docs/git-guide.md`.
