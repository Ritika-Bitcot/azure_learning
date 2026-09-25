#!/usr/bin/env bash
# Provision and deploy the FastAPI CRUD app to Azure Functions (Flex Consumption).
#
#   ./infra/deploy.sh --check   read-only preflight, creates nothing
#   ./infra/deploy.sh           preflight, confirm, provision, configure, publish
#   ./infra/deploy.sh --yes     same, without the confirmation prompt
#
# Env: AZURE_SUBSCRIPTION_ID (default in config.sh), SKIP_TESTS=1 to skip pytest.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=infra/config.sh
source "$ROOT/infra/config.sh"

CHECK_ONLY=false
ASSUME_YES=false
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=true ;;
    --yes) ASSUME_YES=true ;;
    *) die "Unknown argument: $arg (use --check or --yes)" ;;
  esac
done

PROVIDERS=(Microsoft.Web Microsoft.Storage Microsoft.DocumentDB Microsoft.Insights Microsoft.OperationalInsights)

exists_in_rg() {  # <resource-type> <name>
  local count
  count="$(az resource list -g "$RESOURCE_GROUP" --resource-type "$1" \
    --query "[?name=='$2'] | length(@)" -o tsv 2>/dev/null || true)"
  [[ "$count" == "1" ]]
}

web_name_available() {
  az rest --method post \
    --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Web/checknameavailability?api-version=2022-03-01" \
    --body "{\"name\": \"$FUNCTION_APP\", \"type\": \"Microsoft.Web/sites\"}" \
    --query nameAvailable -o tsv
}

# ---------------------------------------------------------------- preflight
preflight() {
  log "P1  Local tools"
  command -v az >/dev/null || die "Azure CLI not found: curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"
  command -v func >/dev/null || die "Azure Functions Core Tools not found: https://learn.microsoft.com/azure/azure-functions/functions-run-local"
  [[ "$(func --version)" == 4.* ]] || die "Azure Functions Core Tools v4 required (found $(func --version))"
  command -v python3.11 >/dev/null || die "python3.11 not found on PATH"
  if ! az extension show -n application-insights >/dev/null 2>&1; then
    if $CHECK_ONLY; then warn "az extension application-insights missing (deploy installs it)"
    else az extension add -n application-insights --only-show-errors; fi
  fi
  ok "az $(az version --query '"azure-cli"' -o tsv), func $(func --version), python3.11"

  log "P2  Azure login"
  az account show >/dev/null 2>&1 || die "Not logged in. Run: az login"
  ok "signed in as $(az account show --query user.name -o tsv)"

  log "P3  Subscription"
  use_subscription
  ok "$(az account show --query name -o tsv) ($SUBSCRIPTION_ID)"

  log "P4  Resource providers"
  local provider state
  for provider in "${PROVIDERS[@]}"; do
    state="$(az provider show -n "$provider" --query registrationState -o tsv)"
    if [[ "$state" == "Registered" ]]; then ok "$provider"
    elif $CHECK_ONLY; then warn "$provider is $state (deploy registers it)"
    else az provider register -n "$provider" --wait >/dev/null || die "Could not register $provider"; ok "$provider registered"
    fi
  done

  log "P5  Flex Consumption region"
  [[ "$(az functionapp list-flexconsumption-locations --query "[?name=='$LOCATION'] | length(@)" -o tsv)" == "1" ]] \
    || die "Region $LOCATION does not support Flex Consumption"
  ok "$LOCATION supports Flex Consumption"

  log "P6  Python runtime on Flex"
  [[ "$(az functionapp list-flexconsumption-runtimes --location "$LOCATION" --runtime python \
      --query "[?version=='$PYTHON_VERSION'] | length(@)" -o tsv)" -ge 1 ]] \
    || die "Python $PYTHON_VERSION is not available on Flex Consumption in $LOCATION"
  ok "python $PYTHON_VERSION available in $LOCATION"

  log "P7  Globally unique names"
  if exists_in_rg Microsoft.Storage/storageAccounts "$STORAGE_ACCOUNT"; then ok "$STORAGE_ACCOUNT (already ours)"
  elif [[ "$(az storage account check-name -n "$STORAGE_ACCOUNT" --query nameAvailable -o tsv)" == "true" ]]; then ok "$STORAGE_ACCOUNT available"
  else die "Storage name $STORAGE_ACCOUNT is taken; change STORAGE_ACCOUNT in infra/config.sh (e.g. ${STORAGE_ACCOUNT}001)"
  fi
  if exists_in_rg Microsoft.DocumentDB/databaseAccounts "$COSMOS_ACCOUNT"; then ok "$COSMOS_ACCOUNT (already ours)"
  elif [[ "$(az cosmosdb check-name-exists -n "$COSMOS_ACCOUNT" -o tsv)" == "false" ]]; then ok "$COSMOS_ACCOUNT available"
  else die "Cosmos name $COSMOS_ACCOUNT is taken; change COSMOS_ACCOUNT in infra/config.sh (e.g. $COSMOS_ACCOUNT-001)"
  fi
  if exists_in_rg Microsoft.Web/sites "$FUNCTION_APP"; then ok "$FUNCTION_APP (already ours)"
  elif [[ "$(web_name_available)" == "true" ]]; then ok "$FUNCTION_APP available"
  else die "Function App name $FUNCTION_APP is taken; change FUNCTION_APP in infra/config.sh (e.g. $FUNCTION_APP-001)"
  fi

  log "P8  Cosmos DB free tier"
  if exists_in_rg Microsoft.DocumentDB/databaseAccounts "$COSMOS_ACCOUNT"; then
    [[ "$(az cosmosdb show -g "$RESOURCE_GROUP" -n "$COSMOS_ACCOUNT" --query enableFreeTier -o tsv)" == "true" ]] \
      || die "$COSMOS_ACCOUNT exists WITHOUT free tier and is being billed. Run ./infra/teardown.sh"
    ok "$COSMOS_ACCOUNT is on the free tier"
  else
    local holder
    holder="$(az cosmosdb list --query "[?enableFreeTier].name | [0]" -o tsv)"
    [[ -z "$holder" ]] || die "The subscription's one Cosmos DB free-tier slot is used by '$holder'. Delete it or use another subscription; this script never creates a paid account."
    ok "free tier slot is available"
  fi

  log "P9  Tests"
  if [[ "${SKIP_TESTS:-}" == "1" ]]; then warn "skipped (SKIP_TESTS=1)"
  else
    [[ -x "$ROOT/.venv/bin/python" ]] || die "No .venv found; see README (python3.11 -m venv .venv)"
    (cd "$ROOT" && .venv/bin/python -m pytest -q) || die "Tests failed; not deploying"
    ok "pytest passed"
  fi

  log "P10 Summary"
  cat <<SUMMARY
    subscription   $(az account show --query name -o tsv) ($SUBSCRIPTION_ID)
    signed in as   $(az account show --query user.name -o tsv)
    region         $LOCATION
    resource group $RESOURCE_GROUP
    storage        $STORAGE_ACCOUNT
    log analytics  $LOG_WORKSPACE
    app insights   $APP_INSIGHTS
    cosmos         $COSMOS_ACCOUNT / $COSMOS_DATABASE / $COSMOS_CONTAINER ($COSMOS_THROUGHPUT RU/s shared, free tier)
    function app   $FUNCTION_APP (Flex Consumption, python $PYTHON_VERSION)
SUMMARY
}

# ---------------------------------------------------------------- provision
provision() {
  log "Resource group"
  az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --tags workload=fastapi-crud env=dev -o none
  ok "$RESOURCE_GROUP"

  log "Storage account"
  exists_in_rg Microsoft.Storage/storageAccounts "$STORAGE_ACCOUNT" || az storage account create \
    -n "$STORAGE_ACCOUNT" -g "$RESOURCE_GROUP" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 \
    --min-tls-version TLS1_2 --allow-blob-public-access false -o none
  ok "$STORAGE_ACCOUNT"

  log "Log Analytics workspace + Application Insights"
  exists_in_rg Microsoft.OperationalInsights/workspaces "$LOG_WORKSPACE" || az monitor log-analytics workspace create \
    -g "$RESOURCE_GROUP" -n "$LOG_WORKSPACE" -l "$LOCATION" -o none
  local workspace_id
  workspace_id="$(az monitor log-analytics workspace show -g "$RESOURCE_GROUP" -n "$LOG_WORKSPACE" --query id -o tsv)"
  exists_in_rg Microsoft.Insights/components "$APP_INSIGHTS" || az monitor app-insights component create \
    --app "$APP_INSIGHTS" -g "$RESOURCE_GROUP" -l "$LOCATION" --workspace "$workspace_id" \
    --application-type web -o none
  ok "$LOG_WORKSPACE, $APP_INSIGHTS"

  log "Cosmos DB account (free tier; takes several minutes)"
  exists_in_rg Microsoft.DocumentDB/databaseAccounts "$COSMOS_ACCOUNT" || az cosmosdb create \
    -n "$COSMOS_ACCOUNT" -g "$RESOURCE_GROUP" \
    --locations regionName="$LOCATION" failoverPriority=0 isZoneRedundant=False \
    --enable-free-tier true --default-consistency-level Session -o none
  if [[ "$(az cosmosdb show -g "$RESOURCE_GROUP" -n "$COSMOS_ACCOUNT" --query enableFreeTier -o tsv)" != "true" ]]; then
    die "!!! $COSMOS_ACCOUNT was created WITHOUT the free tier and WILL BE BILLED. Delete it now: ./infra/teardown.sh"
  fi
  ok "$COSMOS_ACCOUNT (free tier confirmed)"

  log "Cosmos DB database + container"
  az cosmosdb sql database show -a "$COSMOS_ACCOUNT" -g "$RESOURCE_GROUP" -n "$COSMOS_DATABASE" >/dev/null 2>&1 \
    || az cosmosdb sql database create -a "$COSMOS_ACCOUNT" -g "$RESOURCE_GROUP" -n "$COSMOS_DATABASE" \
      --throughput "$COSMOS_THROUGHPUT" -o none
  az cosmosdb sql container show -a "$COSMOS_ACCOUNT" -g "$RESOURCE_GROUP" -d "$COSMOS_DATABASE" -n "$COSMOS_CONTAINER" >/dev/null 2>&1 \
    || az cosmosdb sql container create -a "$COSMOS_ACCOUNT" -g "$RESOURCE_GROUP" -d "$COSMOS_DATABASE" \
      -n "$COSMOS_CONTAINER" --partition-key-path /id --idx "@$ROOT/infra/cosmos-index-policy.json" -o none
  ok "$COSMOS_DATABASE / $COSMOS_CONTAINER"

  log "Function App (Flex Consumption)"
  # --disable-app-insights: we own App Insights above, so the CLI must not create a second one.
  exists_in_rg Microsoft.Web/sites "$FUNCTION_APP" || az functionapp create \
    -n "$FUNCTION_APP" -g "$RESOURCE_GROUP" --storage-account "$STORAGE_ACCOUNT" \
    --flexconsumption-location "$LOCATION" --runtime python --runtime-version "$PYTHON_VERSION" \
    --disable-app-insights -o none
  ok "$FUNCTION_APP"
}

# ---------------------------------------------------------------- configure + publish
configure_and_publish() {
  log "App settings"
  local endpoint key insights
  endpoint="$(az cosmosdb show -g "$RESOURCE_GROUP" -n "$COSMOS_ACCOUNT" --query documentEndpoint -o tsv)"
  key="$(az cosmosdb keys list -g "$RESOURCE_GROUP" -n "$COSMOS_ACCOUNT" --type keys --query primaryMasterKey -o tsv)"
  insights="$(az monitor app-insights component show --app "$APP_INSIGHTS" -g "$RESOURCE_GROUP" --query connectionString -o tsv)"
  az functionapp config appsettings set -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" -o none --settings \
    "COSMOS_ENDPOINT=$endpoint" "COSMOS_KEY=$key" \
    "COSMOS_DATABASE=$COSMOS_DATABASE" "COSMOS_CONTAINER=$COSMOS_CONTAINER" \
    "APPLICATIONINSIGHTS_CONNECTION_STRING=$insights"
  ok "COSMOS_*, APPLICATIONINSIGHTS_CONNECTION_STRING"

  log "Publish code (remote build)"
  # Venv first on PATH so Core Tools sees the project's Python 3.11, not the system python3.
  (cd "$ROOT" && PATH="$ROOT/.venv/bin:$PATH" func azure functionapp publish "$FUNCTION_APP" --python)

  log "Waiting for /api/health"
  local base attempt
  base="https://$(az functionapp show -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" --query defaultHostName -o tsv)"
  for attempt in $(seq 1 36); do
    if curl -fsS "$base/api/health" 2>/dev/null | grep -q '"database":"configured"'; then
      ok "healthy after ~$((attempt * 5))s"
      printf '\nAPI:  %s/api/items\nDocs: %s/api/docs\nSmoke test: ./infra/smoke.sh %s\n' "$base" "$base" "$base"
      return 0
    fi
    sleep 5
  done
  die "$base/api/health did not report a configured database within 3 minutes; check App Insights logs"
}

preflight
if $CHECK_ONLY; then
  printf '\nPreflight passed. Nothing was created.\n'
  exit 0
fi
if ! $ASSUME_YES; then
  read -r -p $'\nProceed with deployment? [y/N] ' answer
  [[ "$answer" == "y" ]] || { echo "Aborted."; exit 0; }
fi
provision
configure_and_publish
