# Setup guide (new engineer, about 1 hour)

Result: the pipeline runs end to end in your Azure Databricks workspace and Power BI reads the Gold tables.
Names below are the ones this PoC actually uses (same as `infra/poc.env`, `databricks.yml` and the
notebook defaults; full list in the README "Naming" section). Keep them consistent. The catalog is
`dpe_azure_poc`, **not** `main`.

| Thing | Name |
|---|---|
| Resource group | `dpe-azure-poc` (region `southeastasia`) |
| Storage account (ADLS Gen2) | `dpeazurepoc` |
| Container | `landing` |
| Access connector | `ac-dpe-azure-poc` |
| Unity Catalog | catalog `dpe_azure_poc`, schema `novacart_poc` (dev: `novacart_poc_dev`), volume `landing` |

## Fast path: scripts (steps 1–3)

Edit `infra/poc.env` (names, subscription, workspace URL), then from the repo root:

```bash
az login
bash infra/01_azure_setup.sh            # storage, container, access connector, role, upload 2025 files
bash infra/02_databricks_uc_setup.sh    # credential, external location, schema, volume, list files
```

Both scripts skip anything that already exists, so they are safe to re-run. Still manual: the budget alert
(step 1) and, if your account lacks rights, the role assignment / Unity Catalog grants by an admin.
The manual portal steps below do the same thing.

## 0. Prerequisites (5 min)

- Azure subscription access with permission to create resources in one resource group.
- Azure Databricks **Premium** workspace with Unity Catalog and serverless enabled (or an admin who can do step 2).
- Python 3.10+, Git, Azure CLI (`az login`). Optional: Databricks CLI ≥ 0.230 for step 4B.
- Power BI Desktop (Windows).

## 1. Cost guardrails and storage (15 min)

Do this **before** creating anything else.

```bash
az group create -n dpe-azure-poc -l southeastasia --tags project=dpe-azure-poc owner=sakib
```

Budget alert: Azure portal → **Cost Management → Budgets → + Add**, scope = the resource group,
monthly amount (e.g. 30 USD), alerts at 50 %, 80 %, 100 % to your email.

```bash
az storage account create -n dpeazurepoc -g dpe-azure-poc -l southeastasia \
  --sku Standard_LRS --kind StorageV2 --hierarchical-namespace true \
  --min-tls-version TLS1_2 --allow-blob-public-access false \
  --tags project=dpe-azure-poc owner=sakib
az storage fs create -n landing --account-name dpeazurepoc --auth-mode login
```

Tag the Databricks workspace (and its managed resource group) with the same two tags.

## 2. Unity Catalog access to the storage (10 min, workspace admin)

No keys or SAS tokens: access goes through a managed identity.

1. Create the **Access Connector for Azure Databricks** `ac-dpe-azure-poc` in the resource group and give its managed identity the role **Storage Blob Data Contributor** on the storage account.
2. Databricks → **Catalog → External data → Credentials → Create credential**: type *Azure Managed Identity*, name `cred_novacart`, paste the access connector resource ID.
3. **External locations → Create**: name `loc_novacart_landing`, URL `abfss://landing@dpeazurepoc.dfs.core.windows.net/`, credential `cred_novacart`. Click *Test connection* (the two optional *File Events* checks may fail; use **Force create**).
4. In a SQL editor:

```sql
CREATE SCHEMA IF NOT EXISTS dpe_azure_poc.novacart_poc;
CREATE EXTERNAL VOLUME IF NOT EXISTS dpe_azure_poc.novacart_poc.landing
  LOCATION 'abfss://landing@dpeazurepoc.dfs.core.windows.net/novacart';
```

## 3. Upload the dataset (5 min)

Catalog Explorer → `dpe_azure_poc` → `novacart_poc` → volume `landing` → create folder `raw` → **Upload to this volume**:
the 9 files of `NOVACART_MINI_V2` (7 CSV + 2 JSON). Do **not** upload `data/demo_batch_2026_01/` yet; that is for the live demo.

Optional local check first: `python tools/check_dataset_contract.py <dataset folder>`.

## 4. Get the code and run the pipeline (15 min)

Databricks → **Settings → Linked accounts → Add Git credential** (GitHub), then
**Workspace → Create → Git folder** with `https://github.com/SakibulBjit11492/retail_e_commerce.git`.
Later updates: branch button → **Pull**.

**A. Notebooks by hand (first time):** open each notebook, set widgets `catalog` / `schema` / `volume`, run in order on serverless:
`00_verify_access` → `01_ingest_bronze` → `02_transform_silver` → `03_build_gold` → `04_validate_quality`.
The last notebook must end with `Data quality: N/N checks passed.`

**B. As one job (recommended after the first run):**

```bash
databricks auth login --host https://adb-<id>.<n>.azuredatabricks.net
databricks bundle validate
databricks bundle deploy -t dev
databricks bundle run novacart_pipeline -t dev
```

This creates the job *novacart-medallion-pipeline* (5 tasks, serverless, tagged, schedule paused).
Without the CLI: **Workflows → Create job**, add the 5 notebooks as tasks in order and the job parameters
`catalog`, `schema`, `volume`, `batch_id` = `{{job.run_id}}`, `force_reload` = `false`.

## 5. Power BI (15 min)

1. Databricks → **SQL Warehouses → Create**: size *2X-Small*, type *Serverless*, **Auto stop 10 min**, tags as above.
2. Warehouse → **Connection details**: copy *Server hostname* and *HTTP path*.
3. Power BI Desktop → **Get data → Azure Databricks**, paste them, mode **Import**, sign in with Microsoft Entra ID.
4. Run [`sql/novacart_bi_views.sql`](../sql/novacart_bi_views.sql) once (creates schema `novacart_bi` with one view per Gold table).
   Either publish it from Databricks (Catalog → `dpe_azure_poc` → `novacart_bi` → **Use with BI tools → Publish to Power BI workspace**,
   workspace `dpe-azure-poc`), or in Power BI Desktop's Navigator open catalog **`dpe_azure_poc`** (not `main`) → schema **`novacart_bi`**.
   Then paste [`powerbi/relationships.tmdl`](../powerbi/relationships.tmdl) (TMDL view) and [`powerbi/measures.dax`](../powerbi/measures.dax) (DAX query view). Details in
   [`data-model.md`](data-model.md) and [`measures.md`](measures.md).

## 6. End of day

Check **Compute** and **SQL Warehouses**: nothing running. Screenshot Cost Management at the end of each week.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `00_verify_access` cannot list the volume | Check external location test, volume path, and that you have `READ VOLUME` on it |
| `No raw file found for: [...]` | A file is missing or misnamed in `raw/` (names must match `<entity>_*.csv` / `*.json`) |
| `01` says *skipped: files already in Bronze* | Expected for a re-run; set `force_reload=true` to append again (no double counting) |
| `04` fails | Read the `FAIL` lines; details are also in `dpe_azure_poc.novacart_poc.dq_results` |
