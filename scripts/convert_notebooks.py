#!/usr/bin/env python3
"""Convert Databricks source .py notebooks to .ipynb with markdown before every code cell."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_NB = ROOT / "src" / "notebooks"
SRC_PY = ROOT / "notebooks"


def split_commands(text: str) -> list[str]:
    text = re.sub(r"^# Databricks notebook source\n", "", text)
    parts = re.split(r"\n# COMMAND ----------\n", text)
    return [p.strip("\n") for p in parts if p.strip()]


def is_md(cell: str) -> bool:
    lines = [ln for ln in cell.splitlines() if ln.strip()]
    if not lines:
        return False
    return lines[0].startswith("# MAGIC %md") or all(
        ln.startswith("# MAGIC %md") or ln.startswith("# MAGIC") for ln in lines[:1]
    ) and "%md" in lines[0]


def to_markdown(cell: str) -> str:
    out = []
    for ln in cell.splitlines():
        if ln.startswith("# MAGIC %md"):
            rest = ln[len("# MAGIC %md") :]
            if rest.startswith(" "):
                rest = rest[1:]
            out.append(rest)
        elif ln.startswith("# MAGIC "):
            out.append(ln[len("# MAGIC ") :])
        elif ln.startswith("# MAGIC"):
            out.append(ln[len("# MAGIC") :].lstrip())
        else:
            out.append(ln)
    md = "\n".join(out)
    md = re.sub(r"(?m)^\s*---\s*$", "", md)
    return md.strip() + "\n"


def to_code(cell: str) -> str:
    return cell.rstrip() + "\n"


def ensure_md_before_code(cells: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result = []
    last_was_code = False
    for i, (kind, src) in enumerate(cells):
        if kind == "code":
            if not result or last_was_code:
                preview = src.strip().splitlines()[0][:80] if src.strip() else "next cell"
                result.append(("markdown", f"Runs the next step.\n\n`{preview}`\n"))
            result.append((kind, src))
            last_was_code = True
        else:
            result.append((kind, src))
            last_was_code = False
    return result


def convert_file(path: Path) -> Path:
    raw = path.read_text(encoding="utf-8")
    chunks = split_commands(raw)
    cells_t: list[tuple[str, str]] = []
    for chunk in chunks:
        stripped = chunk.lstrip()
        if stripped.startswith("# MAGIC %md"):
            cells_t.append(("markdown", to_markdown(chunk)))
        else:
            cells_t.append(("code", to_code(chunk)))
    cells_t = ensure_md_before_code(cells_t)
    nb_cells = []
    for kind, src in cells_t:
        nb_cells.append(
            {
                "cell_type": kind,
                "metadata": {},
                "source": src.splitlines(keepends=True) or [src],
                **({"outputs": [], "execution_count": None} if kind == "code" else {}),
            }
        )
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        },
        "cells": nb_cells,
    }
    SRC_NB.mkdir(parents=True, exist_ok=True)
    dest = SRC_NB / (path.stem + ".ipynb")
    dest.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    return dest


def main():
    names = [
        "_config.py",
        "01_Generate_Synthetic_Data.py",
        "02_Vector_Search_Index.py",
        "03_Sub_Agents.py",
        "04_Supervisor_Agent.py",
        "05_Eval_And_Cost.py",
    ]
    for name in names:
        p = SRC_PY / name
        if not p.exists():
            raise SystemExit(f"missing {p}")
        dest = convert_file(p)
        print(f"wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
