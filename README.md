# Items API — FastAPI CRUD on Azure Functions + Cosmos DB

A FastAPI CRUD API for **items**, running on **Azure Functions** (Flex Consumption, Python 3.11)
and storing data in **Azure Cosmos DB for NoSQL** (free tier). Design: `../docs/superpowers/specs/2026-09-25-fastapi-crud-azure-design.md`.

All commands below run from this folder (`fastapi-crud/`).

| Method | Path | Result |
|---|---|---|
| GET | `/api/health` | `{"status": "ok", "database": "configured" \| "not_configured"}` |
| POST | `/api/items` | 201 + item (`Location` header) |
| GET | `/api/items?limit=50` | Newest first (1–100, default 50) |
| GET | `/api/items/{id}` | 200 / 404 |
| PATCH | `/api/items/{id}` | Partial update; `{}` → 422; `"description": null` clears it |
| DELETE | `/api/items/{id}` | 204 / 404 |

Interactive docs: `/api/docs`.

## Setup (once)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp local.settings.example.json local.settings.json
```

## Test

```bash
.venv/bin/python -m pytest
```

No Azure account or database is needed: the tests use an in-memory repository and a mocked Cosmos SDK.

## Run locally

```bash
source .venv/bin/activate
func start
```

Open http://localhost:7071/api/docs. With no Cosmos settings in `local.settings.json`, item routes
return `503 Database not configured` — that is expected before you deploy.

To try the whole API locally with an in-memory store instead:

```bash
.venv/bin/uvicorn tests.local_inmemory_app:app --port 8000
./infra/smoke.sh http://localhost:8000
```

## Deploy to Azure

Prerequisites: `az login` done, `.venv` set up. All names and the region live in `infra/config.sh`.

```bash
./infra/deploy.sh --check   # read-only preflight: nothing is created
./infra/deploy.sh           # preflight, confirm, provision, configure, publish
```

The preflight stops before creating anything if: tools are missing, you are not logged in, the
subscription is wrong or disabled, `eastus2` or Python 3.11 is not available on Flex Consumption,
a resource name is taken, **the subscription's single Cosmos DB free-tier slot is already used**
(the script never creates a paid account), or the tests fail.

It creates, in resource group `rg-fastapi-crud-dev-eus2` (East US 2):

| Resource | Name |
|---|---|
| Storage account | `stfastapicruddeveus2` |
| Log Analytics / Application Insights | `log-fastapi-crud-dev-eus2` / `appi-fastapi-crud-dev-eus2` |
| Cosmos DB (free tier) | `cosmos-fastapi-crud-dev-eus2` → database `appdb` (1000 RU/s shared) → container `items` (partition key `/id`) |
| Function App (Flex Consumption) | `func-fastapi-crud-dev-eus2` |

When it finishes it prints the API URL. Then:

```bash
./infra/smoke.sh https://<printed-host>
```

To work locally against the real database after deploying:
`func azure functionapp fetch-app-settings func-fastapi-crud-dev-eus2` (writes the Cosmos settings
into `local.settings.json`, which is gitignored).

## Remove everything

```bash
./infra/teardown.sh
```

Deletes the whole resource group.

## Notes

- **Cost.** Flex Consumption bills per execution (with a monthly free grant); the Cosmos DB free
  tier covers 1000 RU/s and 25 GB. Keep the database at 1000 RU/s — more is billed.
- **Partition key `/id`.** Get/patch/delete are single-partition point operations (~1 RU). Listing is
  a cross-partition query; fine at this scale (one physical partition). If listing ever dominates,
  move to a partition key that matches the access pattern (e.g. `/category`) — that needs a new
  container and a data migration.
- **Timestamps** are UTC strings with exactly six fraction digits and a `Z`
  (`2026-09-25T10:15:30.123456Z`), so string order is time order.
- **Auth.** Endpoints are anonymous — this is a learning project. Add auth before real use.
