import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sql_guard import SqlGuardError, sanitize_sql

CATALOG = "sandbox"
SCHEMA = "mfg_quality_agent"


def test_allows_select_on_qualified_table():
    sql = sanitize_sql(
        f"SELECT plant_name, ftq_rate FROM {CATALOG}.{SCHEMA}.plant_metrics LIMIT 20",
        CATALOG,
        SCHEMA,
    )
    assert "plant_metrics" in sql


def test_strips_markdown_fence_and_trailing_semicolon():
    raw = f"""```sql
SELECT COUNT(*) AS n FROM {CATALOG}.{SCHEMA}.defect_history
;
```"""
    sql = sanitize_sql(raw, CATALOG, SCHEMA)
    assert sql.startswith("SELECT")
    assert ";" not in sql


def test_allows_cte_then_select():
    raw = f"""
    WITH recent AS (
      SELECT plant_name, severity FROM {CATALOG}.{SCHEMA}.defect_history
    )
    SELECT severity, COUNT(*) AS n FROM recent GROUP BY severity
    """
    sql = sanitize_sql(raw, CATALOG, SCHEMA)
    assert "WITH" in sql.upper()


def test_rejects_insert():
    with pytest.raises(SqlGuardError, match="read-only"):
        sanitize_sql(
            f"INSERT INTO {CATALOG}.{SCHEMA}.defect_history SELECT * FROM {CATALOG}.{SCHEMA}.defect_history",
            CATALOG,
            SCHEMA,
        )


def test_rejects_multiple_statements():
    with pytest.raises(SqlGuardError, match="Multiple"):
        sanitize_sql(
            f"SELECT 1 FROM {CATALOG}.{SCHEMA}.plant_metrics; DROP TABLE {CATALOG}.{SCHEMA}.plant_metrics",
            CATALOG,
            SCHEMA,
        )


def test_rejects_unqualified_table():
    with pytest.raises(SqlGuardError, match="Unqualified"):
        sanitize_sql("SELECT * FROM defect_history", CATALOG, SCHEMA)


def test_rejects_other_catalog():
    with pytest.raises(SqlGuardError, match="outside"):
        sanitize_sql("SELECT * FROM other.mfg_quality_agent.defect_history", CATALOG, SCHEMA)


def test_rejects_empty():
    with pytest.raises(SqlGuardError, match="empty"):
        sanitize_sql("   ", CATALOG, SCHEMA)
