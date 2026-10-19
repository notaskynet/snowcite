"""Shared test fixtures.

Every test that touches the DB gets an isolated, tmp-dir project. The project
resolver (`snowcite.storage.projects.find_project_root`) supports the
`SNOWCITE_PROJECT_ROOT` env override — we set it per-test via monkeypatch.
"""

from pathlib import Path

import pytest

from snowcite.container import container
from snowcite.storage.projects import create_project_dir


@pytest.fixture
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Scaffold a fresh .snowcite/ under tmp_path and make it the active project."""
    create_project_dir(tmp_path)
    monkeypatch.setenv("SNOWCITE_PROJECT_ROOT", str(tmp_path))
    # The db module caches which paths have had schema applied; clear so
    # Database.init runs for this fresh tmp DB.
    container.db.reset()
    return tmp_path
