"""OHLCV input adapters for the backtest engine.

Two paths are supported:

1. :func:`fetch_ohlcv_via_ccxt` pulls historical bars from a ccxt exchange,
   paginating ``since`` so multi-month / multi-year ranges work. Results are
   cached as Parquet under ``cache_dir`` so reruns are free.
2. :func:`load_ohlcv_csv` loads a CSV with columns
   ``[timestamp, open, high, low, close, volume]`` (timestamp may be epoch
   ms or ISO string).

Both return a tz-aware ``pandas.DataFrame`` indexed 0..N-1 with
``timestamp`` as a UTC datetime column. Dataframes from these helpers are
deduped on timestamp and sorted ascending.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def _to_utc_ms(dt: datetime | str | int | float) -> int:
    if isinstance(dt, (int, float)):
        return int(dt)
    if isinstance(dt, str):
        parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    raise TypeError(f"Unsupported datetime input: {dt!r}")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True, errors="coerce")
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    df = df.dropna(subset=["timestamp"])
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df.reset_index(drop=True)


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    """Load OHLCV from a CSV. The first 6 columns must be the standard set."""
    df = pd.read_csv(path)
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    return _normalize(df[OHLCV_COLUMNS])


def fetch_ohlcv_via_ccxt(
    exchange: Any,
    symbol: str,
    timeframe: str,
    start: datetime | str,
    end: datetime | str,
    *,
    cache_dir: str | None = None,
    page_limit: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV from a ccxt exchange between ``start`` and ``end``.

    The function paginates by ``since`` so it can span months or years.
    When ``cache_dir`` is provided, results are saved to / loaded from a
    Parquet file keyed on (exchange.id, symbol, timeframe, start, end).
    """
    start_ms = _to_utc_ms(start)
    end_ms = _to_utc_ms(end)
    if start_ms >= end_ms:
        raise ValueError("start must be before end")

    cache_path: str | None = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        safe_symbol = symbol.replace("/", "_")
        # CSV is universal; parquet would be smaller but adds an optional dep.
        fname = f"{exchange.id}_{safe_symbol}_{timeframe}_{start_ms}_{end_ms}.csv"
        cache_path = os.path.join(cache_dir, fname)
        if os.path.exists(cache_path):
            logger.info("Loading cached OHLCV from %s", cache_path)
            return load_ohlcv_csv(cache_path)

    rows: list[list[Any]] = []
    cursor = start_ms
    empty_batches = 0
    while cursor < end_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=page_limit)
        if not batch:
            empty_batches += 1
            # Allow up to N consecutive empty batches before giving up — some
            # exchanges return [] for ranges that have no listed bars yet.
            if empty_batches >= 3:
                break
            # Advance cursor by one timeframe to skip empty range; estimate
            # using the timeframe in seconds.
            cursor += int(exchange.parse_timeframe(timeframe) * 1000)
            continue
        empty_batches = 0
        rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:
            # No forward progress; bail to avoid infinite loop.
            break
        cursor = last_ts + 1

    df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    df = df[df["timestamp"] < end_ms]
    df = _normalize(df)

    if cache_path:
        # Persist as ms-epoch in the timestamp column so we don't depend on
        # tz-aware CSV parsing on reload.
        out = df.copy()
        out["timestamp"] = out["timestamp"].astype("int64") // 1_000_000
        out.to_csv(cache_path, index=False)
        logger.info("Cached OHLCV to %s", cache_path)
    return df
