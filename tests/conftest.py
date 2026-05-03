"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys

import pytest

# Make repo root importable when running ``pytest`` from a clone.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Redirect persistent state files to a tmp directory per test."""
    state_file = tmp_path / "state.json"
    log_file = tmp_path / "trades.log"
    monkeypatch.setenv("STATE_FILE", str(state_file))
    monkeypatch.setenv("LOG_FILE", str(log_file))
    # Reload config so changes apply.
    import importlib

    import config

    importlib.reload(config)
    yield


@pytest.fixture
def fresh_trader(monkeypatch, tmp_path):
    """Create a PaperTrader with deterministic, small capital and no fees by default."""
    monkeypatch.setenv("INITIAL_CAPITAL", "1000")
    monkeypatch.setenv("LEVERAGE", "10")
    monkeypatch.setenv("MAX_LEVERAGE", "10")
    monkeypatch.setenv("POSITION_SIZE_PCT", "33")
    monkeypatch.setenv("MAX_POSITIONS", "3")
    monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "20")
    monkeypatch.setenv("TAKE_PROFIT_PCT", "5")
    monkeypatch.setenv("STOP_LOSS_PCT", "5")
    monkeypatch.setenv("TAKER_FEE_PCT", "0.0")
    monkeypatch.setenv("SLIPPAGE_BPS", "0.0")
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "trades.log"))

    import importlib

    import config
    import paper_trader

    importlib.reload(config)
    importlib.reload(paper_trader)

    return paper_trader.PaperTrader()
