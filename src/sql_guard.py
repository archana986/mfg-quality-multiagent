"""Read-only SQL guardrails for LLM-generated warehouse queries."""

from __future__ import annotations

import re

ALLOWED_TABLES = (
    "defect_history",
    "plant_metrics",
    "corrective_actions",
    "quality_inspections",
    "service_bulletins",
    "classifier_results",
    "classifier_scored",
)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|GRANT|REVOKE|"
    r"COPY|TRUNCATE|PUT|REMOVE|UNDROP|RESTORE|VACUUM|OPTIMIZE|CALL|"
    r"EXECUTE|MSCK|SET|USE|REFRESH|UNSET|COMMENT|REPLACE|CLONE)\b",
    re.IGNORECASE,
)

_IDENT = re.compile(
    r"(?i)(?:FROM|JOIN)\s+([`\"\[]?[A-Za-z0-9_]+[`\"\]]?(?:\.[`\"\[]?[A-Za-z0-9_]+[`\"\]]?){0,2})"
)


class SqlGuardError(ValueError):
    """Raised when generated SQL is not a permitted read-only query."""


def sanitize_sql(raw: str, catalog: str, schema: str) -> str:
    """Strip markdown fences and accept a single SELECT/CTE against this schema only."""
    if not raw or not str(raw).strip():
        raise SqlGuardError("SQL is empty")
    if not catalog or not schema:
        raise SqlGuardError("catalog and schema are required")

    sql = str(raw).strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    sql = sql.strip().rstrip(";")
    if not sql:
        raise SqlGuardError("SQL is empty")
    if ";" in sql:
        raise SqlGuardError("Multiple SQL statements are not allowed")
    if _FORBIDDEN.search(sql):
        raise SqlGuardError("Only read-only SELECT queries are allowed")

    first = sql.lstrip("(").lstrip()
    if not re.match(r"(?is)^(WITH|SELECT)\b", first):
        raise SqlGuardError("Only SELECT or WITH (CTE) queries are allowed")

    expected_prefix = f"{catalog}.{schema}.".lower()
    allowed = {name.lower() for name in ALLOWED_TABLES}
    refs = _IDENT.findall(sql)
    qualified_hits = 0

    for raw_ref in refs:
        ref = raw_ref.replace("`", "").replace('"', "").replace("[", "").replace("]", "")
        parts = [p for p in ref.split(".") if p]
        if len(parts) == 3:
            prefix = f"{parts[0]}.{parts[1]}.".lower()
            table = parts[2].lower()
            if prefix != expected_prefix:
                raise SqlGuardError(f"Table {ref} is outside {catalog}.{schema}")
            if table not in allowed:
                raise SqlGuardError(f"Table {ref} is not in the allowed quality dataset")
            qualified_hits += 1
        elif len(parts) == 1 and parts[0].lower() in allowed:
            raise SqlGuardError(
                f"Unqualified table {parts[0]} is not allowed; use {catalog}.{schema}.{parts[0]}"
            )
        elif len(parts) == 2:
            raise SqlGuardError(f"Table {ref} must be fully qualified as {catalog}.{schema}.<table>")
        # One-part names that are not physical tables are treated as CTE aliases.

    if qualified_hits == 0:
        raise SqlGuardError("Query must reference a fully qualified table in the configured schema")

    return sql
