# shellcheck shell=bash
# Shared settings for deploy.sh / teardown.sh. Names follow the Cloud Adoption
# Framework pattern <type>-<workload>-<env>-<region>.
# shellcheck disable=SC2034  # variables are used by the scripts that source this file
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-d80c315f-69c7-407b-9c4c-e93fdee9e2ad}"
LOCATION="eastus2"
PYTHON_VERSION="3.11"

RESOURCE_GROUP="rg-fastapi-crud-dev-eus2"
STORAGE_ACCOUNT="stfastapicruddeveus2"
LOG_WORKSPACE="log-fastapi-crud-dev-eus2"
APP_INSIGHTS="appi-fastapi-crud-dev-eus2"
COSMOS_ACCOUNT="cosmos-fastapi-crud-dev-eus2"
COSMOS_DATABASE="appdb"
COSMOS_CONTAINER="items"
COSMOS_THROUGHPUT=1000  # shared database throughput == the free-tier allowance
FUNCTION_APP="func-fastapi-crud-dev-eus2"

log() { printf '\n==> %s\n' "$*"; }
ok() { printf '    ok: %s\n' "$*"; }
warn() { printf '    warn: %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

use_subscription() {
  local state
  state="$(az account list --all --query "[?id=='$SUBSCRIPTION_ID'].state | [0]" -o tsv)"
  if [[ -z "$state" ]]; then
    az account list --all --query "[].{name:name, id:id, state:state}" -o table >&2
    die "Subscription $SUBSCRIPTION_ID is not available to this login (set AZURE_SUBSCRIPTION_ID)"
  fi
  [[ "$state" == "Enabled" ]] || die "Subscription $SUBSCRIPTION_ID is $state, not Enabled"
  az account set --subscription "$SUBSCRIPTION_ID"
  [[ "$(az account show --query id -o tsv)" == "$SUBSCRIPTION_ID" ]] || die "Could not switch to $SUBSCRIPTION_ID"
}
