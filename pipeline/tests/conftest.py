from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from voltia import db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_json() -> Callable[[str], Any]:
    def _load(name: str) -> Any:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def read_text() -> Callable[[str], str]:
    def _read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _read


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = db.make_engine(f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}")
    db.migrate(eng)
    return eng
