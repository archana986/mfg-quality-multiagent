"""Shared supervisor tools and agent loop for notebooks and the Databricks App."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from sql_guard import SqlGuardError, sanitize_sql

ExecuteSql = Callable[[str], list[dict]]

CLASSIFY_PROMPT = """Classify this manufacturing inspection using ONLY these categories:

SEVERITY: Critical (safety/quarantine), Major (out of spec/rework), Minor (borderline/monitor), None (within spec)
ROOT CAUSE: Material, Process, Equipment, Human, or None

Return JSON: {{"severity": "...", "root_cause": "...", "corrective_action": "one sentence", "reasoning": "one sentence"}}

INSPECTION: {inspection_notes}"""

SQL_SCHEMA_TEMPLATE = """Tables in {catalog}.{schema}:
- defect_history: defect_id, defect_date, plant_id, plant_name, line, shift, part_type, severity, root_cause, status, rework_cost_usd, resolution_days, affected_units
- plant_metrics: metric_date, plant_id, plant_name, ftq_rate, oee_rate, throughput_units, scrap_count, rework_count, unplanned_downtime_min
- corrective_actions: action_id, inspection_id, plant_id, part_type, action_type, status, severity, action_date, completion_date
- quality_inspections: inspection_id, inspection_date, plant_name, line, part_type, measurement_value, spec_min, spec_max, defect_notes"""

SQL_GEN_PROMPT = """Convert to Databricks SQL. Use fully qualified names ({catalog}.{schema}.<table>).
ONLY return a single SELECT or WITH query. No DDL/DML. Limit 20 rows.

{table_schemas}

Question: {question}

SQL:"""

SUPERVISOR_SYSTEM = """You are a Manufacturing Quality Assistant for an automotive assembly plant.
You help technicians and quality engineers investigate defects, find fixes, and understand trends.

You have 3 tools:
1. classify_defect — Classify new defect reports (severity + root cause)
2. search_service_bulletins — Find relevant service bulletins and historical fixes
3. query_quality_data — Query structured data (defect trends, plant KPIs, costs)

For complex questions, use MULTIPLE tools.

After collecting tool results, synthesize a clear, technician-friendly answer with:
- Severity assessment (if applicable)
- Root cause analysis
- Recommended actions (step by step)
- Data context (trends, costs, volumes)
- Service bulletin references

Be specific. Cite bulletin IDs, plant names, and numbers."""


def table_schemas(catalog: str, schema: str) -> str:
    return SQL_SCHEMA_TEMPLATE.format(catalog=catalog, schema=schema)


@dataclass
class Supervisor:
    llm: Any
    tools: list
    system_prompt: str = SUPERVISOR_SYSTEM

    def run(self, user_question: str, max_iterations: int = 5, collect_steps: bool = False):
        llm_with_tools = self.llm.bind_tools(self.tools)
        tool_map = {t.name: t for t in self.tools}
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_question},
        ]
        steps: list[dict] = []
        for _ in range(max_iterations):
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            if not getattr(response, "tool_calls", None):
                content = response.content
                return (content, steps) if collect_steps else content
            for tool_call in response.tool_calls:
                name = tool_call["name"]
                args = tool_call["args"]
                steps.append({"tool": name, "args": args})
                result = tool_map[name].invoke(args)
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
        msg = "Max iterations reached. Please refine your question."
        return (msg, steps) if collect_steps else msg


def build_supervisor(
    llm: Any,
    catalog: str,
    schema: str,
    vs_index: str,
    execute_sql: ExecuteSql,
    workspace_client: Optional[Any] = None,
) -> Supervisor:
    """Bind classify / retrieve / SQL tools to one supervisor LLM."""

    @tool
    def classify_defect(inspection_notes: str) -> str:
        """Classify a manufacturing defect from inspection notes.
        Returns severity (Critical/Major/Minor/None), root cause, and recommended corrective action."""
        return llm.invoke(CLASSIFY_PROMPT.format(inspection_notes=inspection_notes)).content

    @tool
    def search_service_bulletins(defect_description: str) -> str:
        """Search service bulletins for relevant fixes and procedures."""
        from databricks.sdk import WorkspaceClient

        w = workspace_client or WorkspaceClient()
        results = w.vector_search_indexes.query_index(
            index_name=vs_index,
            columns=[
                "bulletin_id",
                "part_type",
                "failure_mode",
                "severity_level",
                "priority",
                "bulletin_text",
            ],
            query_text=defect_description,
            num_results=3,
        )
        bulletins = []
        for row in results.result.data_array:
            bulletins.append(
                {
                    "bulletin_id": row[0],
                    "part_type": row[1],
                    "failure_mode": row[2],
                    "severity": row[3],
                    "priority": row[4],
                    "text": str(row[5])[:500],
                    "relevance_score": round(float(row[-1]), 4),
                }
            )
        return json.dumps(bulletins, indent=2)

    @tool
    def query_quality_data(question: str) -> str:
        """Query structured manufacturing quality data using natural language. Read-only SELECT only."""
        schemas = table_schemas(catalog, schema)
        raw_sql = llm.invoke(
            SQL_GEN_PROMPT.format(
                catalog=catalog, schema=schema, table_schemas=schemas, question=question
            )
        ).content
        try:
            sql = sanitize_sql(raw_sql, catalog, schema)
            rows = execute_sql(sql)
            return json.dumps({"sql": sql, "results": rows, "row_count": len(rows)}, default=str)
        except SqlGuardError as e:
            return json.dumps({"error": str(e), "sql": str(raw_sql)})
        except Exception as e:
            return json.dumps({"sql": str(raw_sql), "error": str(e)})

    return Supervisor(llm=llm, tools=[classify_defect, search_service_bulletins, query_quality_data])
