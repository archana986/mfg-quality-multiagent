# Setup: Manufacturing Quality Multi-Agent Assistant

Use this project as a starting point in **your** Databricks workspace. Clone or copy the folder, set variables, deploy the bundle, run setup, then open the app.

## Prerequisites

- Databricks CLI 0.292 or later (`databricks -v`)
- `databricks auth login --host <your-workspace-url>` (OAuth; do not use a PAT)
- A Unity Catalog catalog you can write (the job creates a **schema**, not a catalog)
- A SQL warehouse you can use
- Access to Foundation Model endpoints named in the bundle variables (or override them)
- Vector Search entitlement

## Configure

Edit nothing in notebooks for catalog/schema. Pass values at deploy time:

```bash
cd mfg-quality-multiagent

databricks bundle validate --strict -t dev \
  --var catalog=<catalog> \
  --var warehouse_id=<warehouse_id>
```

| Variable | What to set |
|----------|-------------|
| `catalog` | Catalog you can create a schema in |
| `warehouse_id` | Warehouse ID from **SQL > Warehouses** |
| `schema` | Optional; default `mfg_quality_agent` |
| `llm_endpoint` | Optional serving endpoint for the supervisor |
| `embedding_endpoint` | Optional embedding endpoint for Vector Search |
| `vs_endpoint` | Optional Vector Search endpoint name |

The CLI profile must match **your** workspace URL. This repo does not pin a host.

## Deploy and run

```bash
databricks bundle deploy -t dev --var catalog=<catalog> --var warehouse_id=<warehouse_id>
databricks bundle run setup -t dev
databricks bundle run quality_assistant -t dev
```

Optional (Foundation Model cost): `databricks bundle run eval -t dev`

If the app resource cannot bind the vector index on the first deploy, run `setup`, then `bundle deploy` again.

## Customize for your own project

- Change synthetic generators in `src/notebooks/01_Generate_Synthetic_Data.ipynb`
- Change routing or prompts in `src/agent_runtime.py` (shared by notebooks and the app)
- Change the Streamlit UI in `src/app.py`
- Add job tasks in `resources/setup.job.yml` or `resources/eval.job.yml`

## Known limitations

- **No catalog create:** you must already have a writable catalog.
- **Cloud-agnostic jobs:** serverless only. Classic node types are not used.
- **App SQL:** text-to-SQL runs on the attached warehouse, not Databricks Connect. The app service principal needs `USE CATALOG`, `USE SCHEMA`, and `SELECT` on `<catalog>.<schema>` and the vector index.
- **Vector Search name:** default endpoint name may already exist in a busy workspace. Override `vs_endpoint`.
- **Foundation Model names:** `databricks-claude-sonnet-4-5` and `databricks-gte-large-en` must exist or be overridden.
- **Notebook packages:** notebooks 02-05 install `databricks-langchain` and `langchain-core` with `%pip`. Jobs do not use a custom `environment_key` (that path can stall serverless startup).
- **Billing tables:** optional; need `SELECT` on `system.billing.usage`. Data can lag hours.
- **App env catalog:** `src/app.yaml` has fallback literals. Bundle `resources/app.yml` `config.env` is what deploy applies for `MFG_CATALOG` / `MFG_SCHEMA`.
- **Prod target:** uses `run_as` as the deploying user. Point production at a service principal if your org requires it.

## Layout

| Path | Use |
|------|-----|
| `src/notebooks/` | Databricks notebooks (`.ipynb`) |
| `src/app.py` | Streamlit app |
| `src/agent_runtime.py` | Shared supervisor tools |
| `src/sql_guard.py` | Read-only SQL checks |
| `resources/` | Jobs and app bundle definitions |
| `databricks.yml` | Bundle name, variables, targets |
