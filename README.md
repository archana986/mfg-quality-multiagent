# Manufacturing Quality Multi-Agent Assistant

Fork this repository, point it at your Databricks workspace, and deploy a working multi-agent quality assistant on a clean schema. All data is **synthetic**. No customer plant data is included.

This README is the GitHub source of truth. `databricks bundle deploy` uploads the notebooks, jobs, and app. It does **not** publish this README or the architecture image into the workspace. Read here first, then deploy.

## What this proves

A technician asks one plain-language question. A supervisor model decides which specialist tools to call, runs them, and returns one answer with severity, root cause, recommended steps, data context, and service bulletin IDs.

- **Classifier** (`classify_defect`): turns free-text inspection notes into severity (Critical, Major, Minor, None), root cause, and a corrective action.
- **Retriever** (`search_service_bulletins`): finds the three most relevant service bulletins through Vector Search.
- **SQL agent** (`query_quality_data`): converts a question to read-only SQL and runs it on a SQL warehouse against your quality tables.

The same tool code (`src/agent_runtime.py`) runs in the notebooks and in the Databricks App, so what you test in a notebook is what the app runs.

## Architecture

![Setup job builds synthetic tables and a Vector Search index in Unity Catalog. In the Databricks App, a supervisor model routes each question to retrieve, classify, and query tools and returns one answer with sources. Text-to-SQL passes a SQL guard before the SQL warehouse. An optional eval job reuses the same tools.](docs/diagrams/mfg_quality_multiagent.png)

Editable source: [`docs/diagrams/mfg_quality_multiagent.svg`](docs/diagrams/mfg_quality_multiagent.svg).

| Stage | What it is | What it does |
|---|---|---|
| 1. Synthetic data | Notebook 01, seeded generators | Creates five tables: `quality_inspections`, `defect_history`, `plant_metrics`, `corrective_actions`, `service_bulletins`. |
| 2. Vector Search | Notebook 02, Delta Sync index | Creates the endpoint if missing, enables Change Data Feed, and indexes `service_bulletins.bulletin_text` with `databricks-gte-large-en`. |
| 3. Supervisor + tools | Notebooks 03 and 04, `src/agent_runtime.py` | Exercises each sub-agent, then the tool-calling supervisor (up to 5 steps), and logs the run to MLflow. |
| 4. Databricks App | Streamlit, `src/app.py` | Technician UI. Runs text-to-SQL on the attached SQL warehouse and queries the vector index. |
| 5. Optional eval | Notebook 05, separate job | Classifier scorecard, a 12-question agent eval, and an optional billing cost query. |
| Guardrails | `src/sql_guard.py` | Allows only a single `SELECT` or `WITH` statement against fully qualified tables in `<catalog>.<schema>`. |
| Governance | Unity Catalog | Tables and the index live in your catalog and schema. The app service principal needs read grants. |

## Use in your workspace

Set these for your environment:

| Value | Where | Example |
|---|---|---|
| Databricks CLI profile | `-p <profile>` after `databricks auth login` | your profile name |
| `catalog` | bundle `--var` | any catalog where you can create a schema |
| `schema` | optional `--var` | `mfg_quality_agent` (default) |
| `warehouse_id` | required `--var` | ID from **SQL > SQL Warehouses** |
| `llm_endpoint` | optional `--var` | `databricks-claude-sonnet-4-5` (default) |
| `embedding_endpoint` | optional `--var` | `databricks-gte-large-en` (default) |
| `vs_endpoint` | optional `--var` | `mfg_quality_vs_endpoint` (default) |

```bash
git clone https://github.com/archana986/mfg-quality-multiagent.git
cd mfg-quality-multiagent

databricks auth login --host <your-workspace-url> -p <profile>

databricks bundle validate --strict -t dev -p <profile> \
  --var catalog=<your_catalog> --var warehouse_id=<warehouse-id>

databricks bundle deploy -t dev -p <profile> \
  --var catalog=<your_catalog> --var warehouse_id=<warehouse-id>

# Data, Vector Search index, sub-agents, supervisor (notebooks 01 to 04)
databricks bundle run setup -t dev -p <profile> \
  --var catalog=<your_catalog> --var warehouse_id=<warehouse-id>

# Start or update the app
databricks bundle run quality_assistant -t dev -p <profile> \
  --var catalog=<your_catalog> --var warehouse_id=<warehouse-id>
```

Optional evaluation (calls Foundation Models; default 50 inspections):

```bash
databricks bundle run eval -t dev -p <profile> \
  --var catalog=<your_catalog> --var warehouse_id=<warehouse-id>
```

After the first deploy, grant the app service principal read access. Use the principal's **client ID** (shown on the app's page), not its display name:

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA <catalog>.<schema> TO `<app-sp-client-id>`;
```

Open the app URL from the deploy output or **Compute > Apps**. Prerequisites, customization, and known limits: [SETUP.md](SETUP.md).

Local checks (no Databricks call):

```bash
python -m venv .venv && source .venv/bin/activate
pip install pytest langchain-core
pytest
```

### Interactive path (no job)

1. Deploy the bundle once so the notebooks land in your workspace, or import `src/notebooks/` manually.
2. Attach serverless compute. Set the `catalog` and `schema` widgets on each notebook.
3. Run notebooks 01, 02, 03, 04 in order. Run 05 only when you want an eval.

## Adopt (bring your own data)

The synthetic generator is only for the out-of-the-box demo. To use your own tables:

1. Keep the same table and column contract, or update `SQL_SCHEMA_TEMPLATE` in `src/agent_runtime.py` so the SQL agent sees your real columns.
2. Point notebook 02 at your bulletin or knowledge table. It needs a primary key and a text column to embed.
3. Keep every table in one `<catalog>.<schema>`. The SQL guard rejects queries outside it.
4. Retune the classifier prompt and categories in `CLASSIFY_PROMPT` for your defect taxonomy, then re-run the eval job.
5. Re-grant the app service principal on any new schema.

## Update (after you change code or pull)

| Change | What to do |
|---|---|
| Pull latest from GitHub | `git pull`, then `bundle deploy` and `bundle run setup` again with the same vars |
| Notebook or resource YAML edits | `databricks bundle deploy`, then rerun the job |
| App code (`src/app.py`, `src/agent_runtime.py`) | `databricks bundle deploy`; the app redeploys from `src/` |
| Different catalog or schema for one run | pass `--var` on the CLI |
| Defaults for a target | edit `variables` / `targets` in `databricks.yml`, then validate and deploy |
| Remove jobs and app only | `databricks bundle destroy` (does **not** drop Unity Catalog tables or the Vector Search endpoint) |
| Drop demo data | `DROP SCHEMA <catalog>.<schema> CASCADE` on a schema dedicated to this demo, and delete the Vector Search endpoint if nothing else uses it |

## What each repo file does

| Path | Role |
|---|---|
| `databricks.yml` | Bundle name, variables (`catalog`, `schema`, `warehouse_id`, endpoints), `dev` and `prod` targets. No pinned workspace host. |
| `resources/setup.job.yml` | Serverless setup job (notebooks 01 then 02 then 03 then 04). |
| `resources/eval.job.yml` | Optional eval job (notebook 05). |
| `resources/app.yml` | Databricks App: Streamlit command, env vars, SQL warehouse and serving endpoint resources. |
| `src/notebooks/_config.ipynb` | Shared widgets and puts `src/` on `sys.path`. |
| `src/notebooks/01_Generate_Synthetic_Data.ipynb` | Creates the schema and five synthetic tables. |
| `src/notebooks/02_Vector_Search_Index.ipynb` | Vector Search endpoint and Delta Sync index. |
| `src/notebooks/03_Sub_Agents.ipynb` | Tests the classifier, retriever, and SQL agent one by one. |
| `src/notebooks/04_Supervisor_Agent.ipynb` | Tests the supervisor end to end and logs to MLflow. |
| `src/notebooks/05_Eval_And_Cost.ipynb` | Optional eval and billing query. |
| `src/agent_runtime.py` | Shared supervisor loop and the three tools. |
| `src/sql_guard.py` | Read-only SQL checks. |
| `src/notebook_bootstrap.py` | Widget and path helpers for notebooks. |
| `src/app.py`, `src/app.yaml`, `src/requirements.txt` | Streamlit app, start command, dependencies. |
| `tests/` | Local tests for the SQL guard, bootstrap, agent runtime, and notebook structure. |
| `scripts/convert_notebooks.py` | Maintainer tool used to convert source notebooks to `.ipynb`. |
| `docs/diagrams/` | Architecture PNG (this README) and its editable SVG source. |
| `multi_genie_*.mmd` / `.png` | Background concept diagrams of supervisor patterns (managed Supervisor Agent vs code-first). Not part of the deploy. |
| `SETUP.md` | Prerequisites, customization, known limitations. |

## Validation status

Tested on an Azure Databricks workspace with serverless jobs:

- `bundle validate --strict` and `bundle deploy` succeed. The app reaches **RUNNING**.
- Local tests pass (SQL guard, bootstrap, agent runtime, notebook structure).
- Setup job succeeds end to end (data generation, Vector Search index, sub-agents, supervisor) in about 8 minutes on a warm Vector Search endpoint. The first endpoint provision can take much longer.
- Eval job run on 2026-10-04 (synthetic data, default 50 inspections):
  - Classifier scorecard: severity 74%, root cause 100%, both correct 74%, 0 unparseable. Most misses label Major as Critical.
  - Agent eval, 12 questions: 91.7% overall (classification 3/3, retrieval 3/3, SQL 3/4, hybrid 2/2). Logged to MLflow.
  - These are synthetic-data results, not production accuracy. Re-run in your workspace for current numbers.

## Limitations

- You must already have a writable catalog. The job only runs `CREATE SCHEMA`.
- Jobs are serverless only. No classic node types are defined.
- The first Vector Search endpoint can take many minutes to provision. Notebook 02 waits until the index is ready.
- Model names must exist in your workspace, or be overridden with `--var`.
- Eval and classifier cells call Foundation Models and incur usage. Keep `eval_sample_size` small.
- The billing query needs `SELECT` on `system.billing.usage` and can lag hours. The eval job continues if it fails. It filters on `identity_metadata.run_as` (an earlier version referenced a non-existent `run_as_identity` field and always failed). Results are totals for that identity across all its workloads, not only this demo.
- Re-running setup fails with `ResourceAlreadyExists` if `service_bulletins_index` already exists. Delete the index (`databricks vector-search-indexes delete-index <catalog>.<schema>.service_bulletins_index`) and re-run.

## References

- [Databricks Asset Bundles](https://docs.databricks.com/aws/en/dev-tools/bundles/)
- [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Mosaic AI Vector Search](https://docs.databricks.com/aws/en/generative-ai/vector-search)
- [Foundation Model APIs](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/)

## License

Demo code and synthetic data are provided as-is for internal reuse. Add an organization-approved license if you redistribute outside that audience.
