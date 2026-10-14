"""Static checks on the Databricks .ipynb notebooks (no Databricks call)."""

import json
from pathlib import Path

import pytest

NOTEBOOK_DIR = Path(__file__).resolve().parent.parent / "src" / "notebooks"
NOTEBOOKS = sorted(NOTEBOOK_DIR.glob("*.ipynb"))
STAGE_NOTEBOOKS = [p for p in NOTEBOOKS if p.name[:2].isdigit()]
PIP_NOTEBOOKS = [p for p in STAGE_NOTEBOOKS if p.name[:2] in {"02", "03", "04", "05"}]


def _cells(path):
    return json.loads(path.read_text())["cells"]


def _code_cells(path):
    return [c for c in _cells(path) if c["cell_type"] == "code"]


def test_notebooks_found():
    assert len(STAGE_NOTEBOOKS) == 5


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_no_magic_comment_prefix_in_ipynb(path):
    # In .ipynb, "# MAGIC %run" is a plain comment and silently never runs.
    for cell in _code_cells(path):
        for line in cell["source"]:
            assert not line.startswith("# MAGIC"), f"{path.name}: {line.strip()}"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_every_code_cell_has_markdown_before_it(path):
    cells = _cells(path)
    assert cells[0]["cell_type"] == "markdown"
    for i, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            assert cells[i - 1]["cell_type"] == "markdown", f"{path.name}: cell {i}"


@pytest.mark.parametrize("path", STAGE_NOTEBOOKS, ids=lambda p: p.name)
def test_stage_notebooks_run_config(path):
    sources = ["".join(c["source"]).strip() for c in _code_cells(path)]
    assert "%run ./_config" in sources


@pytest.mark.parametrize("path", PIP_NOTEBOOKS, ids=lambda p: p.name)
def test_pip_is_first_code_cell(path):
    first = "".join(_code_cells(path)[0]["source"]).lstrip()
    assert first.startswith("%pip install")


def test_missing_markdown_is_detected(tmp_path):
    bad = tmp_path / "bad.ipynb"
    bad.write_text(json.dumps({"cells": [
        {"cell_type": "markdown", "source": ["# t\n"]},
        {"cell_type": "code", "source": ["x = 1\n"]},
        {"cell_type": "code", "source": ["y = 2\n"]},
    ]}))
    with pytest.raises(AssertionError):
        test_every_code_cell_has_markdown_before_it(bad)
