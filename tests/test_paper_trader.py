"""Unit tests for PaperTrader."""

from __future__ import annotations

import threading


def test_open_and_close_long_no_fees(fresh_trader):
    pos = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    assert "error" not in pos
    assert pos["leverage"] == 10
    assert pos["margin"] > 0
    assert fresh_trader.locked_capital > 0

    # Price moves +10% — that's +100% PnL on margin at 10x leverage.
    closed = fresh_trader.close_position("BTC/USDT", exit_price=110.0, reason="MANUAL")
    assert closed["pnl"] > 0
    # PnL should be roughly 10x of margin (10% gain on the *position size*),
    # i.e. ~100% return on margin.
    assert closed["pnl_pct"] > 90
    assert "BTC/USDT" not in fresh_trader.positions


def test_open_and_close_short_no_fees(fresh_trader):
    """Mirror of the LONG happy path. SHORT profits when price drops."""
    pos = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="SELL")
    assert "error" not in pos
    assert pos["type"] == "SELL"
    assert pos["leverage"] == 10
    # Default fallback: TP below entry, SL above entry.
    assert pos["take_profit"] < pos["entry_price"]
    assert pos["stop_loss"] > pos["entry_price"]
    # Liquidation must be ABOVE entry for shorts.
    assert pos["liquidation_price"] > pos["entry_price"]

    # Price drops 5% — short PnL is positive, on margin ~50% return at 10x.
    closed = fresh_trader.close_position("BTC/USDT", exit_price=95.0, reason="MANUAL")
    assert closed["pnl"] > 0
    assert closed["pnl_pct"] > 40
    assert "BTC/USDT" not in fresh_trader.positions


def test_short_uses_inverted_liquidation(fresh_trader):
    """SHORT liq must be on the upside (entry * (1 + 1/L - buffer))."""
    pos = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="SELL")
    # 10x leverage, 0.5% buffer -> liq ~= entry * 1.095
    expected = 100.0 * (1 + 1 / 10 - 0.005)
    # Allow some slack for entry-side slippage applied to fill_price.
    assert abs(pos["liquidation_price"] - expected) / expected < 0.01


def test_short_check_positions_uses_high_sl(fresh_trader):
    """For SHORTs, candle HIGH must trigger SL even if last < SL."""
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="SELL")
    pos = fresh_trader.positions["BTC/USDT"]
    sl = pos.stop_loss
    closed = fresh_trader.check_positions({
        "BTC/USDT": {"high": sl + 0.5, "low": 99.0, "last": 100.2},
    })
    assert len(closed) == 1
    assert closed[0]["close_reason"] == "STOP_LOSS"


def test_short_check_positions_uses_low_tp(fresh_trader):
    """For SHORTs, candle LOW must trigger TP even if last > TP."""
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="SELL")
    pos = fresh_trader.positions["BTC/USDT"]
    tp = pos.take_profit
    closed = fresh_trader.check_positions({
        "BTC/USDT": {"high": 100.5, "low": tp - 0.5, "last": 99.8},
    })
    assert len(closed) == 1
    assert closed[0]["close_reason"] == "TAKE_PROFIT"


def test_short_trailing_stop_only_moves_down(fresh_trader):
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="SELL")
    pos = fresh_trader.positions["BTC/USDT"]
    initial_sl = pos.stop_loss

    # Price up against us: no trailing.
    update = fresh_trader.update_trailing_stop("BTC/USDT", current_price=101.0)
    assert update is None
    assert fresh_trader.positions["BTC/USDT"].stop_loss == initial_sl

    # 5% in our favour (price down): SL should move *down* toward current price.
    update = fresh_trader.update_trailing_stop("BTC/USDT", current_price=95.0)
    assert update is not None
    assert update["new_sl"] < initial_sl

    # Price reverses up to 97: trailing must NOT loosen (move up).
    new_sl = fresh_trader.positions["BTC/USDT"].stop_loss
    update = fresh_trader.update_trailing_stop("BTC/USDT", current_price=97.0)
    assert update is None
    assert fresh_trader.positions["BTC/USDT"].stop_loss == new_sl


def test_long_and_short_can_coexist(fresh_trader):
    """Concurrent LONG and SHORT positions on different symbols."""
    fresh_trader.max_positions = 5
    long_pos = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    short_pos = fresh_trader.open_position("ETH/USDT", entry_price=2000.0, signal_type="SELL")
    assert "error" not in long_pos
    assert "error" not in short_pos
    assert long_pos["type"] == "BUY"
    assert short_pos["type"] == "SELL"
    # Both directions priced consistently.
    assert long_pos["take_profit"] > long_pos["entry_price"]
    assert short_pos["take_profit"] < short_pos["entry_price"]


def test_unknown_signal_still_rejected(fresh_trader):
    """Defense in depth: bogus signal types must be refused."""
    result = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="WAT")
    assert result.get("error") == "UNSUPPORTED_SIGNAL"


def test_max_positions_enforced(fresh_trader):
    fresh_trader.max_positions = 2
    a = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    b = fresh_trader.open_position("ETH/USDT", entry_price=2000.0, signal_type="BUY")
    c = fresh_trader.open_position("SOL/USDT", entry_price=50.0, signal_type="BUY")
    assert "error" not in a and "error" not in b
    assert c.get("error") == "RISK_RULE_VIOLATION"


def test_duplicate_position_rejected(fresh_trader):
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    dup = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    assert dup.get("error") == "DUPLICATE_POSITION"


def test_trailing_stop_only_moves_up(fresh_trader):
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    pos = fresh_trader.positions["BTC/USDT"]
    initial_sl = pos.stop_loss

    # Below profit threshold: nothing happens.
    update = fresh_trader.update_trailing_stop("BTC/USDT", current_price=101.0)
    assert update is None
    assert fresh_trader.positions["BTC/USDT"].stop_loss == initial_sl

    # 5% profit: trailing kicks in to 2% behind current price.
    update = fresh_trader.update_trailing_stop("BTC/USDT", current_price=110.0)
    assert update is not None
    assert update["new_sl"] > initial_sl

    # Price drops back to 105 — trailing stop must NOT loosen.
    new_sl = fresh_trader.positions["BTC/USDT"].stop_loss
    update = fresh_trader.update_trailing_stop("BTC/USDT", current_price=105.0)
    assert update is None
    assert fresh_trader.positions["BTC/USDT"].stop_loss == new_sl


def test_position_exposes_leverage_field(fresh_trader):
    """Bug 1.1 regression: leverage must be persisted on the Position dict."""
    pos = fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    assert pos["leverage"] == fresh_trader.leverage


def test_check_positions_uses_candle_high_low(fresh_trader):
    """Liquidation/SL hits triggered by intra-candle low even if last > SL."""
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    pos = fresh_trader.positions["BTC/USDT"]
    sl = pos.stop_loss
    # Last price still above SL, but candle low pierced SL.
    closed = fresh_trader.check_positions({
        "BTC/USDT": {"high": 101.0, "low": sl - 0.5, "last": 100.5},
    })
    assert len(closed) == 1
    assert closed[0]["close_reason"] == "STOP_LOSS"


def test_save_and_load_roundtrip(fresh_trader, tmp_path):
    path = tmp_path / "state.json"
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    fresh_trader.save_state(str(path))

    # Recreate a clean trader; load state.
    import paper_trader
    other = paper_trader.PaperTrader()
    assert other.load_state(str(path)) is True
    assert "BTC/USDT" in other.positions
    assert other.positions["BTC/USDT"].leverage == 10


def test_thread_safety_smoke(fresh_trader):
    """Concurrent open/close must not raise or leave inconsistent state."""
    fresh_trader.max_positions = 50
    errors: list[Exception] = []

    def worker(symbol: str):
        try:
            for _ in range(20):
                fresh_trader.open_position(symbol, entry_price=100.0, signal_type="BUY")
                fresh_trader.close_position(symbol, exit_price=101.0, reason="STRESS")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"COIN{i}/USDT",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert fresh_trader.locked_capital >= 0


def test_daily_loss_limit_blocks_new_positions(fresh_trader):
    fresh_trader.daily_pnl = -fresh_trader.day_start_equity * 0.25  # -25%
    ok, reason = fresh_trader.can_open_position()
    assert not ok
    assert "Daily loss" in reason


def test_close_after_dataclass_roundtrip(fresh_trader, tmp_path):
    """Position loaded from state JSON can still be closed without KeyError."""
    fresh_trader.open_position("BTC/USDT", entry_price=100.0, signal_type="BUY")
    path = tmp_path / "s.json"
    fresh_trader.save_state(str(path))

    import paper_trader
    other = paper_trader.PaperTrader()
    assert other.load_state(str(path)) is True
    closed = other.close_position("BTC/USDT", exit_price=105.0, reason="MANUAL")
    assert "BTC/USDT" not in other.positions
    assert closed["pnl"] > 0
