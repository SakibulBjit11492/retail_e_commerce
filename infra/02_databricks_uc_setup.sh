#!/usr/bin/env bash
# Creates (or reuses) the Unity Catalog objects that let notebooks read the ADLS files:
#   storage credential -> external location -> schema -> external volume, then lists the raw files.
#
# Safe to re-run: existing objects are skipped.
# Needs: Azure CLI (az login, to look up the connector ID) and Databricks CLI >= 0.230
#        (brew tap databricks/tap && brew install databricks), plus metastore rights to create
#        storage credentials / external locations (otherwise ask the workspace admin).
# Usage:  bash infra/02_databricks_uc_setup.sh      (from the repo root)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=poc.env
source "$ROOT/infra/poc.env"
export DATABRICKS_HOST
log() { printf '\n==> %s\n' "$*"; }
URL="abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/"
VOLUME_URL="${URL}${VOLUME_FOLDER}"

log "Databricks login ($DATABRICKS_HOST)"
if ! databricks current-user me -o json >/dev/null 2>&1; then
  databricks auth login --host "$DATABRICKS_HOST"
fi
databricks current-user me -o json | python3 -c "import json,sys; print('Logged in as', json.load(sys.stdin)['userName'])"

CONNECTOR_ID=$(az databricks access-connector show -n "$ACCESS_CONNECTOR" -g "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" --query id -o tsv)

log "Storage credential $CREDENTIAL"
if databricks storage-credentials get "$CREDENTIAL" >/dev/null 2>&1; then
  echo "exists - skipped"
else
  databricks storage-credentials create --json "{
    \"name\": \"$CREDENTIAL\",
    \"comment\": \"NovaCart PoC - managed identity of $ACCESS_CONNECTOR\",
    \"azure_managed_identity\": {\"access_connector_id\": \"$CONNECTOR_ID\"}
  }" >/dev/null
  echo "created"
fi

log "External location $EXTERNAL_LOCATION -> $URL"
if databricks external-locations get "$EXTERNAL_LOCATION" >/dev/null 2>&1; then
  echo "exists - skipped"
else
  # skip_validation = the UI's "Force create": file events (optional) are not configured for this PoC.
  databricks external-locations create --json "{
    \"name\": \"$EXTERNAL_LOCATION\",
    \"url\": \"$URL\",
    \"credential_name\": \"$CREDENTIAL\",
    \"comment\": \"NovaCart PoC landing container\",
    \"skip_validation\": true
  }" >/dev/null
  echo "created"
fi

log "Schema $CATALOG.$SCHEMA"
if databricks schemas get "$CATALOG.$SCHEMA" >/dev/null 2>&1; then
  echo "exists - skipped"
else
  databricks schemas create "$SCHEMA" "$CATALOG" --comment "NovaCart PoC bronze/silver/gold tables" >/dev/null
  echo "created"
fi

log "External volume $CATALOG.$SCHEMA.$VOLUME -> $VOLUME_URL"
if databricks volumes read "$CATALOG.$SCHEMA.$VOLUME" >/dev/null 2>&1; then
  echo "exists - skipped"
else
  databricks volumes create "$CATALOG" "$SCHEMA" "$VOLUME" EXTERNAL \
    --storage-location "$VOLUME_URL" --comment "Raw NovaCart files (raw/ folder)" >/dev/null
  echo "created"
fi

log "Files visible to Databricks in /Volumes/$CATALOG/$SCHEMA/$VOLUME/raw"
databricks fs ls "dbfs:/Volumes/$CATALOG/$SCHEMA/$VOLUME/raw"

log "Done. Notebook widgets: catalog=$CATALOG schema=$SCHEMA volume=$VOLUME"
