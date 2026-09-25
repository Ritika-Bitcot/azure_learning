#!/usr/bin/env bash
# Delete every Azure resource of this app by deleting its resource group.
#   ./infra/teardown.sh [--yes]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=infra/config.sh
source "$ROOT/infra/config.sh"

az account show >/dev/null 2>&1 || die "Not logged in. Run: az login"
use_subscription

if [[ "$(az group exists -n "$RESOURCE_GROUP" -o tsv)" != "true" ]]; then
  echo "Resource group $RESOURCE_GROUP does not exist; nothing to delete."
  exit 0
fi

az resource list -g "$RESOURCE_GROUP" --query "[].{name:name, type:type}" -o table
if [[ "${1:-}" != "--yes" ]]; then
  read -r -p $'\nDelete resource group '"$RESOURCE_GROUP"$' and everything above? [y/N] ' answer
  [[ "$answer" == "y" ]] || { echo "Aborted."; exit 0; }
fi
az group delete -n "$RESOURCE_GROUP" --yes --no-wait
echo "Deletion of $RESOURCE_GROUP started (takes a few minutes)."
