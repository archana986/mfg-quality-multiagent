"""
Manufacturing Quality Assistant — technician UI on Databricks Apps.

Uses Foundation Model serving, Vector Search, and a SQL warehouse.
All data is synthetic. Catalog, schema, and warehouse ID come from app env.
"""

from __future__ import annotations

import os

import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from databricks_langchain import ChatDatabricks

from agent_runtime import build_supervisor

CATALOG = os.environ.get("MFG_CATALOG", "main")
SCHEMA = os.environ.get("MFG_SCHEMA", "mfg_quality_agent")
LLM_MODEL = os.environ.get("MFG_LLM_ENDPOINT", "databricks-claude-sonnet-4-5")
VS_INDEX = os.environ.get("MFG_VS_INDEX", f"{CATALOG}.{SCHEMA}.service_bulletins_index")
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

st.set_page_config(page_title="Quality Assistant", page_icon="🔧", layout="wide")


@st.cache_resource
def get_clients():
    w = WorkspaceClient()
    llm = ChatDatabricks(endpoint=LLM_MODEL, temperature=0.1)
    return w, llm


@st.cache_resource
def get_sql_connection():
    if not WAREHOUSE_ID:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID is not set. Attach a sql-warehouse resource in the bundle."
        )
    from databricks import sql

    cfg = Config()
    host = (cfg.host or os.environ.get("DATABRICKS_HOST") or "").replace("https://", "").replace(
        "http://", ""
    )
    return sql.connect(
        server_hostname=host,
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
        credentials_provider=lambda: cfg.authenticate,
    )


def _run_warehouse_sql(sql_text: str) -> list[dict]:
    conn = get_sql_connection()
    with conn.cursor() as cur:
        cur.execute(sql_text)
        rows = cur.fetchall()
        columns = [c[0] for c in cur.description] if cur.description else []
    records = []
    for row in rows[:20]:
        if hasattr(row, "asDict"):
            records.append(row.asDict())
        else:
            records.append(dict(zip(columns, row)))
    return records


w, llm = get_clients()
supervisor = build_supervisor(
    llm=llm,
    catalog=CATALOG,
    schema=SCHEMA,
    vs_index=VS_INDEX,
    execute_sql=_run_warehouse_sql,
    workspace_client=w,
)


st.title("🔧 Manufacturing Quality Assistant")
st.caption("AI-powered defect analysis, service bulletin lookup, and quality trend insights")

with st.sidebar:
    st.header("Example Questions")
    examples = [
        "Brake rotor at 22.5mm on Line 2 at Arlington. Spec is 28-32mm. What should I do?",
        "Any service bulletins for wiring harness intermittent failures?",
        "Compare FTQ rates across all plants for the last month",
        "Battery module at 2.8V on Line 4 at Spring Hill. Is this known?",
        "Top root causes for critical defects at Flint Assembly?",
        "Paint surface showing orange peel and fish-eye on door panels",
    ]
    for ex in examples:
        if st.button(ex[:60] + "...", key=ex):
            st.session_state["input"] = ex

    st.divider()
    st.header("How It Works")
    st.markdown(
        """
    **3 AI Sub-Agents:**
    1. **Classifier** — Analyzes defect severity and root cause
    2. **Retriever** — Searches service bulletins via Vector Search
    3. **SQL Agent** — Queries quality data trends

    A **Supervisor** routes your question to the right agent(s).
    """
    )
    st.caption(f"Catalog `{CATALOG}.{SCHEMA}`")

user_input = st.text_area(
    "Describe your quality issue or ask a question:",
    value=st.session_state.get("input", ""),
    height=100,
    placeholder="e.g., Brake rotor measured 22.5mm, spec is 28-32mm. What severity and what should I do?",
)

if st.button("🔍 Analyze", type="primary", disabled=not user_input):
    with st.spinner("Analyzing..."):
        answer, steps = supervisor.run(user_input, collect_steps=True)

    if steps:
        st.subheader("Agent Routing")
        cols = st.columns(len(steps))
        tool_icons = {
            "classify_defect": "🏷️",
            "search_service_bulletins": "📋",
            "query_quality_data": "📊",
        }
        for i, step in enumerate(steps):
            with cols[i]:
                icon = tool_icons.get(step["tool"], "🔧")
                st.metric(f"{icon} {step['tool']}", "Called")

    st.divider()
    st.subheader("Analysis")
    st.markdown(answer)

st.divider()
st.caption(
    "Powered by Databricks Foundation Models, Vector Search, and Unity Catalog | All data is synthetic"
)
