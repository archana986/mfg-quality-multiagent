"""Locate bundle `src/` on Databricks so notebooks can import sql_guard and agent_runtime."""

from __future__ import annotations

from pathlib import Path
import sys


def add_src_to_sys_path(dbutils=None) -> str:
    """Put the directory that contains sql_guard.py on sys.path. Returns that directory."""
    candidates: list[Path] = []
    if dbutils is not None:
        try:
            raw = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
            p = Path("/Workspace") / str(raw).lstrip("/")
            candidates.append(p.parent.parent)
            candidates.append(p.parent)
        except Exception:
            pass
    cwd = Path.cwd()
    candidates.extend(
        [
            cwd.parent,
            cwd,
            cwd / "src",
            cwd.parent / "src",
            Path(__file__).resolve().parent,
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        if (Path(resolved) / "sql_guard.py").exists():
            if resolved not in sys.path:
                sys.path.insert(0, resolved)
            return resolved
    raise FileNotFoundError(
        "Could not find sql_guard.py. Deploy this bundle so src/ is next to src/notebooks/."
    )
