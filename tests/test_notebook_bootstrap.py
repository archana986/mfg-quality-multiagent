from pathlib import Path
import sys

from notebook_bootstrap import add_src_to_sys_path


def test_add_src_to_sys_path_finds_sql_guard(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "sql_guard.py").write_text("# stub\n")
    nb = src / "notebooks"
    nb.mkdir()
    monkeypatch.chdir(nb)
    found = add_src_to_sys_path(dbutils=None)
    assert Path(found).resolve() == src.resolve()
    assert str(src.resolve()) in sys.path
