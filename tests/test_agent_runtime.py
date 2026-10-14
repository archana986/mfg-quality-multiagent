import json
from types import SimpleNamespace

from agent_runtime import CLASSIFY_PROMPT, SUPERVISOR_SYSTEM, table_schemas
from sql_guard import sanitize_sql


def test_table_schemas_includes_catalog_schema():
    text = table_schemas("sandbox", "quality")
    assert "sandbox.quality" in text
    assert "defect_history" in text


def test_classify_prompt_injects_notes():
    out = CLASSIFY_PROMPT.format(inspection_notes="rotor thin")
    assert "rotor thin" in out
    assert "JSON" in out


def test_supervisor_system_lists_tools():
    assert "classify_defect" in SUPERVISOR_SYSTEM
    assert "search_service_bulletins" in SUPERVISOR_SYSTEM
    assert "query_quality_data" in SUPERVISOR_SYSTEM


class _Resp:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []


class _LLM:
    def invoke(self, prompt):
        sql = "SELECT plant_name FROM sandbox.quality.plant_metrics LIMIT 5"
        return _Resp(sql)

    def bind_tools(self, tools):
        return self


def test_query_quality_data_tool_uses_sql_guard(monkeypatch):
    try:
        from agent_runtime import build_supervisor
    except ImportError:
        return
    captured = {}

    def execute_sql(sql_text):
        captured["sql"] = sql_text
        return [{"plant_name": "Arlington"}]

    sup = build_supervisor(
        llm=_LLM(),
        catalog="sandbox",
        schema="quality",
        vs_index="sandbox.quality.service_bulletins_index",
        execute_sql=execute_sql,
        workspace_client=SimpleNamespace(),
    )
    tool = next(t for t in sup.tools if t.name == "query_quality_data")
    out = json.loads(tool.invoke({"question": "FTQ by plant"}))
    assert "sql" in out
    assert captured["sql"] == sanitize_sql(captured["sql"], "sandbox", "quality")
    assert out["row_count"] == 1
