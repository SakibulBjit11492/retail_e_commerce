#!/usr/bin/env bash
# Creates (or reuses) the Azure side of the PoC:
#   resource group -> ADLS Gen2 storage account -> container -> Access Connector (managed identity)
#   -> "Storage Blob Data Contributor" for the connector -> upload the 2025 dataset to <container>/novacart/raw
#
# Safe to re-run: every step checks first and skips what already exists.
# Needs: Azure CLI (az login). Assigning the role needs Owner / RBAC Administrator on the storage account.
# Usage:  bash infra/01_azure_setup.sh            (from the repo root)
#         SKIP_UPLOAD=1 bash infra/01_azure_setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=poc.env
source "$ROOT/infra/poc.env"
TAGS=(project="$TAG_PROJECT" owner="$TAG_OWNER")
log() { printf '\n==> %s\n' "$*"; }

log "Azure subscription"
az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{name:name, id:id, user:user.name}" -o table

log "Resource group $RESOURCE_GROUP"
if az group show -n "$RESOURCE_GROUP" -o none 2>/dev/null; then
  echo "exists - skipped"
else
  az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --tags "${TAGS[@]}" -o none
  echo "created"
fi

log "Storage account $STORAGE_ACCOUNT (ADLS Gen2, Standard LRS, Hot)"
if az storage account show -n "$STORAGE_ACCOUNT" -g "$RESOURCE_GROUP" -o none 2>/dev/null; then
  echo "exists - skipped"
else
  az storage account create -n "$STORAGE_ACCOUNT" -g "$RESOURCE_GROUP" -l "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 --access-tier Hot --hns true \
    --min-tls-version TLS1_2 --allow-blob-public-access false \
    --tags "${TAGS[@]}" -o none
  echo "created"
fi
HNS=$(az storage account show -n "$STORAGE_ACCOUNT" -g "$RESOURCE_GROUP" --query isHnsEnabled -o tsv)
[[ "$HNS" == "true" ]] || { echo "ERROR: hierarchical namespace is not enabled on $STORAGE_ACCOUNT"; exit 1; }
STORAGE_ID=$(az storage account show -n "$STORAGE_ACCOUNT" -g "$RESOURCE_GROUP" --query id -o tsv)

log "Container $CONTAINER"
# --auth-mode key uses your Contributor access to read the account key (nothing is stored).
if [[ "$(az storage fs exists -n "$CONTAINER" --account-name "$STORAGE_ACCOUNT" --auth-mode key --query exists -o tsv)" == "true" ]]; then
  echo "exists - skipped"
else
  az storage fs create -n "$CONTAINER" --account-name "$STORAGE_ACCOUNT" --auth-mode key -o none
  echo "created"
fi

log "Access Connector $ACCESS_CONNECTOR (system-assigned managed identity)"
az extension add --name databricks --upgrade --only-show-errors
if az databricks access-connector show -n "$ACCESS_CONNECTOR" -g "$RESOURCE_GROUP" -o none 2>/dev/null; then
  echo "exists - skipped"
else
  az databricks access-connector create -n "$ACCESS_CONNECTOR" -g "$RESOURCE_GROUP" -l "$LOCATION" \
    --identity-type SystemAssigned --tags "${TAGS[@]}" -o none
  echo "created"
fi
CONNECTOR_ID=$(az databricks access-connector show -n "$ACCESS_CONNECTOR" -g "$RESOURCE_GROUP" --query id -o tsv)
PRINCIPAL_ID=$(az databricks access-connector show -n "$ACCESS_CONNECTOR" -g "$RESOURCE_GROUP" --query identity.principalId -o tsv)

log "Role: Storage Blob Data Contributor -> $ACCESS_CONNECTOR"
EXISTING=$(az role assignment list --assignee "$PRINCIPAL_ID" --scope "$STORAGE_ID" \
  --role "Storage Blob Data Contributor" --query "length(@)" -o tsv)
if [[ "$EXISTING" != "0" ]]; then
  echo "exists - skipped"
else
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
    --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" -o none
  echo "assigned (can take ~5 minutes to take effect)"
fi

if [[ "${SKIP_UPLOAD:-0}" != "1" ]]; then
  log "Upload 2025 dataset -> $CONTAINER/$VOLUME_FOLDER/raw"
  # Only the 2025 files: the demo batch (data/demo_batch_2026_01) is uploaded live during the demo.
  az storage blob upload-batch --account-name "$STORAGE_ACCOUNT" --auth-mode key \
    -d "$CONTAINER" --destination-path "$VOLUME_FOLDER/raw" -s "$ROOT/data" \
    --pattern "*_2025*" --overwrite --only-show-errors -o none
  az storage fs file list -f "$CONTAINER" --path "$VOLUME_FOLDER/raw" --account-name "$STORAGE_ACCOUNT" \
    --auth-mode key --query "[].{file:name, bytes:contentLength}" -o table
fi

log "Done. Values for the Databricks step (infra/02_databricks_uc_setup.sh reads them automatically):"
echo "Access connector ID: $CONNECTOR_ID"
echo "Storage URL:         abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/"
echo "Reminder: create the budget alert in Cost Management if not done yet (not scriptable with notifications in az CLI)."
