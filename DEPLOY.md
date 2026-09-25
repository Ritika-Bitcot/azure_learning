# Deploying to Azure: step by step

This guide deploys the app by hand, one Azure resource at a time, and shows how to check each step. `./infra/deploy.sh` runs the same steps automatically; see "Shortcut for later" at the end.

**You need:**
- The Azure CLI, logged in (`az login`)
- Azure Functions Core Tools v4
- The project `.venv` set up (see [README.md](README.md#setup-once))

**Time:** about 20–30 minutes, including a 5–10 minute wait for Cosmos DB.
**Cost:** about $0. The Cosmos DB free tier (1000 RU/s, 25 GB, one free-tier account per subscription) and the Flex Consumption monthly free grant cover it. Step 12 deletes everything.

**What gets created** in resource group `rg-fastapi-crud-dev-eus2` (East US 2):

| Resource | Name | Purpose |
|---|---|---|
| Storage account | `stfastapicruddeveus2` | Functions' code package and internal state |
| Log Analytics + App Insights | `log-fastapi-crud-dev-eus2`, `appi-fastapi-crud-dev-eus2` | Logs, traces, errors |
| Cosmos DB (free tier) | `cosmos-fastapi-crud-dev-eus2` → `appdb` → `items` | The data |
| Function App (Flex Consumption) | `func-fastapi-crud-dev-eus2` | Runs the FastAPI app |

## Step 0: Create `.env` with the deploy variables and load it

Run everything from the app folder:

```bash
cd ~/Desktop/bitcot_projects/azure_learning/fastapi-crud
```

Create `fastapi-crud/.env`, either in your editor or with this command:

```bash
cat > .env <<'EOF'
# Azure deploy variables (resource names only, no secrets). Same values as infra/config.sh.
RG=rg-fastapi-crud-dev-eus2
LOC=eastus2
ST=stfastapicruddeveus2
LOG=log-fastapi-crud-dev-eus2
APPI=appi-fastapi-crud-dev-eus2
COSMOS=cosmos-fastapi-crud-dev-eus2
DB=appdb
CONTAINER=items
FUNC=func-fastapi-crud-dev-eus2
EOF
```

Load it into your terminal and check:

```bash
set -a; source .env; set +a
echo "$RG | $COSMOS | $FUNC"
az account show --query "{subscription:name, user:user.name}" -o table
```

✅ It prints the three names, then your subscription and `<your-azure-login>`. If the subscription is wrong: `az account set --subscription "<name-or-id>"`.
- `set -a` … `set +a` exports every variable from the file, so `az`, `func` and scripts can all see them.
- **New terminal? Run `set -a; source .env; set +a` again.** Variables live only in the terminal that loaded them.
- `.env` is already gitignored (`.gitignore:34`), so it never reaches GitHub. The app doesn't read `.env` (its settings come from `local.settings.json` locally and App settings in Azure), so this file only drives your deploy commands.
- **Keep secrets out of `.env`.** Step 7 fetches the Cosmos key into a temporary shell variable and sends it straight to Azure. It never needs to be written to a file.

## Step 1: Preflight check (reads only, creates nothing)

```bash
./infra/deploy.sh --check
```

✅ Checks P1–P10 all `ok`, ending with `Preflight passed. Nothing was created.` Resources you already created show `(already ours)` at P7. This confirms tools, login, region, Python 3.11 on Flex, free names, the free tier and passing tests.

## Step 2: Resource group and storage account

```bash
az group create -n $RG -l $LOC --tags workload=fastapi-crud env=dev -o none
az storage account create -n $ST -g $RG -l $LOC --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false -o none

az resource list -g $RG --query "[].{name:name, type:type}" -o table
```

✅ It lists `stfastapicruddeveus2  Microsoft.Storage/storageAccounts`. If either already exists, the create command just confirms it.
*What it is:* the resource group is the project folder; `./infra/teardown.sh` deletes it and everything in it. Functions keeps your uploaded code package and its internal state in the storage account.

## Step 3: Logging (Log Analytics + Application Insights)

```bash
az monitor log-analytics workspace create -g $RG -n $LOG -l $LOC -o none
WS_ID=$(az monitor log-analytics workspace show -g $RG -n $LOG --query id -o tsv)
az monitor app-insights component create --app $APPI -g $RG -l $LOC \
  --workspace "$WS_ID" --application-type web -o none
az monitor app-insights component show --app $APPI -g $RG --query provisioningState -o tsv
```

✅ The last command prints `Succeeded`.
*What it is:* App Insights is the logs and traces dashboard for the app, roughly LangSmith for the whole API. Log Analytics is the store underneath it.

## Step 4: Cosmos DB account, free tier (the slow step, 5–10 min)

```bash
az cosmosdb create -n $COSMOS -g $RG \
  --locations regionName=$LOC failoverPriority=0 isZoneRedundant=False \
  --enable-free-tier true --default-consistency-level Session -o none

az cosmosdb show -n $COSMOS -g $RG --query "{freeTier:enableFreeTier, state:provisioningState}" -o table
```

✅ It shows `freeTier: True`, `state: Succeeded`.
⚠️ **If `freeTier` shows `False`, stop and delete it:** `az cosmosdb delete -n $COSMOS -g $RG --yes`. It would be billed.
*What it is:* a serverless JSON document database. It's billed in RU/s, which work like tokens per minute; the free tier gives 1000 RU/s.

## Step 5: Database and container

```bash
az cosmosdb sql database create -a $COSMOS -g $RG -n $DB --throughput 1000 -o none
az cosmosdb sql container create -a $COSMOS -g $RG -d $DB -n $CONTAINER \
  --partition-key-path /id --idx @infra/cosmos-index-policy.json -o none

az cosmosdb sql container show -a $COSMOS -g $RG -d $DB -n $CONTAINER \
  --query "{pk:resource.partitionKey.paths[0], composite:length(resource.indexingPolicy.compositeIndexes)}" -o table
```

✅ It shows `pk: /id`, `composite: 1`.
- `--throughput 1000` goes on the **database** and is shared, which matches the free tier exactly. Don't set throughput on the container, because that would be billed.
- `--idx`: the composite index from `infra/cosmos-index-policy.json` makes the "newest first" list query in `app/repository.py` work.

## Step 6: Function App (Flex Consumption, Python 3.11)

```bash
az functionapp create -n $FUNC -g $RG --storage-account $ST \
  --flexconsumption-location $LOC --runtime python --runtime-version 3.11 \
  --disable-app-insights -o none

az functionapp show -n $FUNC -g $RG --query "{state:properties.state || state, host:properties.defaultHostName || defaultHostName}" -o table
```

✅ It shows `state: Running` and a host name. **Note the host.** Flex may add a unique suffix, so it may not be exactly `func-fastapi-crud-dev-eus2.azurewebsites.net`.
- `--disable-app-insights`: we made App Insights in Step 3, so the CLI must not create a second one. The app is linked to it in Step 7.

## Step 7: App settings (environment variables for the app)

```bash
COSMOS_ENDPOINT=$(az cosmosdb show -n $COSMOS -g $RG --query documentEndpoint -o tsv)
COSMOS_KEY=$(az cosmosdb keys list -n $COSMOS -g $RG --type keys --query primaryMasterKey -o tsv)
APPI_CONN=$(az monitor app-insights component show --app $APPI -g $RG --query connectionString -o tsv)

az functionapp config appsettings set -n $FUNC -g $RG -o none --settings \
  "COSMOS_ENDPOINT=$COSMOS_ENDPOINT" "COSMOS_KEY=$COSMOS_KEY" \
  "COSMOS_DATABASE=$DB" "COSMOS_CONTAINER=$CONTAINER" \
  "APPLICATIONINSIGHTS_CONNECTION_STRING=$APPI_CONN"

az functionapp config appsettings list -n $FUNC -g $RG --query "[?starts_with(name,'COSMOS')].name" -o tsv
```

✅ It lists the four `COSMOS_*` names. The listing deliberately shows names only, not values.
*What it is:* `app/config.py` reads these at runtime. It's the same idea as setting `OPENAI_API_KEY` on a hosting platform: the key stays out of git.

## Step 8: Publish the code

```bash
source .venv/bin/activate
func azure functionapp publish $FUNC --python
```

✅ It ends with `Deployment completed successfully` and lists `http_app_func - [httpTrigger]`.
- `source .venv/bin/activate` makes Core Tools see Python 3.11. Your system `python3` is 3.10.
- Azure pip-installs the pinned `requirements.txt` in the cloud (remote build). `.funcignore` keeps `tests/`, `docs/`, `infra/` and `.venv/` out of the upload.
- The first publish takes about 2–4 minutes.

## Step 9: Verify

```bash
BASE=https://$(az functionapp show -n $FUNC -g $RG --query "properties.defaultHostName || defaultHostName" -o tsv)
curl -s $BASE/api/health; echo
./infra/smoke.sh $BASE
```

✅ Health returns `{"status":"ok","database":"configured"}`. The smoke test prints 11 `ok` lines and `Smoke test passed`.
Also open `$BASE/api/docs` in a browser and try POST / GET / PATCH / DELETE in Swagger.
⏱ The first request after a publish, or after idle time, can take a few seconds (cold start). If health returns 503 or times out, wait about 30 seconds and retry.

## Step 10: Explore what you built (Azure Portal)

1. https://portal.azure.com → **Resource groups** → `rg-fastapi-crud-dev-eus2`: 5 resources.
2. **Cosmos DB** → **Data Explorer** → `appdb` → `items`: see the JSON documents your API wrote. The smoke test deletes its own item, so create one in Swagger first.
3. **Application Insights** → **Live metrics** / **Transaction search**: see each request and any errors.
4. **Function App** → **Environment variables**: the settings from Step 7.

## Step 11 (optional): run locally against the real Cosmos DB

```bash
func azure functionapp fetch-app-settings $FUNC   # writes COSMOS_* into local.settings.json (gitignored)
func start                                        # add --port 7072 if 7071 is busy
curl -s localhost:7072/api/items; echo
```

⚠️ `fetch-app-settings` also copies `AzureWebJobsStorage` and other cloud settings into `local.settings.json`. Keep that file out of git. It is already in `.gitignore`.

## Step 12: Clean up when done

```bash
./infra/teardown.sh
```

It lists the resources, asks `[y/N]` and deletes the whole resource group. That takes a few minutes in the background, and billing stops.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Step 4: `ServiceUnavailable` / "high demand in region" | Cosmos DB capacity is full in eastus2 | Retry later, or change `LOC` for Cosmos only (for example `eastus`) and repeat Step 4 |
| Step 4: "free tier already used" | Another free-tier Cosmos DB account exists | Only one is allowed per subscription. Delete the other one or skip the free tier (billed) |
| Step 6: `The name is already in use` | The Function App name is globally taken | Use `FUNC=func-fastapi-crud-dev-eus2-001` and repeat from Step 6 |
| Step 8: Python version warning | venv not active | Run `source .venv/bin/activate` first |
| Step 9: `"database":"not_configured"` | Step 7 settings are missing or not yet applied | Re-run Step 7, wait about 30 seconds, retry |
| Step 9: 500 errors | App error | App Insights → **Failures**, or Portal → Function App → **Log stream** |

## Shortcut for later

Once you've done it by hand once, `./infra/deploy.sh` runs Steps 1 and 3–9 in one go. It skips what already exists, so it's safe to re-run after any partial deploy.
