"""CLI entry point: ``python -m backtest --symbol BTC/USDT --start ... --end ...``.

Loads OHLCV (CSV or live ccxt), runs the backtest, prints metrics report,
optionally writes equity-curve CSV/PNG and trades CSV.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import pandas as pd

import logging_config
from backtest.data import fetch_ohlcv_via_ccxt, load_ohlcv_csv
from backtest.engine import BacktestSettings, run_backtest
from backtest.metrics import format_report, summarize


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a backtest of the future-simulasi strategy")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", type=str, help="Path to OHLCV CSV (timestamp/open/high/low/close/volume)")
    src.add_argument("--symbol", type=str, help="Symbol to fetch via ccxt (e.g. BTC/USDT)")

    p.add_argument("--exchange", default="binance", help="ccxt exchange id (default: binance)")
    p.add_argument("--market-type", default="future",
                   help="ccxt market type: 'future' (USDT-M perpetuals, default) or 'spot'")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--start", type=str, help="Start ISO date (UTC), e.g. 2024-01-01")
    p.add_argument("--end", type=str, help="End ISO date (UTC), e.g. 2025-01-01")
    p.add_argument("--cache-dir", default=".backtest-cache")

    p.add_argument("--initial-capital", type=float, default=1000.0)
    p.add_argument("--leverage", type=int, default=10)
    p.add_argument("--position-size-pct", type=float, default=0.33)
    p.add_argument("--max-positions", type=int, default=3)
    p.add_argument("--taker-fee-pct", type=float, default=0.04)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--funding-bps-per-8h", type=float, default=0.0)
    p.add_argument("--no-long", action="store_true", help="Disable LONG entries")
    p.add_argument("--no-short", action="store_true", help="Disable SHORT entries")
    p.add_argument("--htf-filter-ma", type=int, default=None,
                   help="If set, require close>MA(N) for LONG and close<MA(N) for SHORT")
    p.add_argument("--warmup-bars", type=int, default=50)

    p.add_argument("--out-dir", default=None,
                   help="Directory to write trades.csv, equity.csv, metrics.json. Optional.")
    p.add_argument("--plot", action="store_true",
                   help="Save equity-curve PNG to out-dir (requires matplotlib)")
    p.add_argument("--symbol-label", default=None,
                   help="Override the symbol label used in the report title")
    return p.parse_args(argv)


def _load_data(args: argparse.Namespace) -> tuple[pd.DataFrame, str]:
    if args.csv:
        df = load_ohlcv_csv(args.csv)
        label = args.symbol_label or os.path.basename(args.csv)
        return df, label

    if not (args.symbol and args.start and args.end):
        raise SystemExit("--symbol requires --start and --end")
    import ccxt
    exchange_cls = getattr(ccxt, args.exchange)
    exchange = exchange_cls({
        "enableRateLimit": True,
        "options": {"defaultType": args.market_type},
    })
    df = fetch_ohlcv_via_ccxt(
        exchange,
        args.symbol,
        args.timeframe,
        start=args.start,
        end=args.end,
        cache_dir=args.cache_dir,
    )
    label = args.symbol_label or args.symbol
    return df, label


def _save_outputs(out_dir: str, label: str, equity_curve: pd.Series, trades: list, metrics_dict: dict, plot: bool) -> None:
    os.makedirs(out_dir, exist_ok=True)
    equity_path = os.path.join(out_dir, "equity.csv")
    equity_curve.to_csv(equity_path, header=True)

    trades_path = os.path.join(out_dir, "trades.csv")
    pd.DataFrame(trades).to_csv(trades_path, index=False)

    metrics_path = os.path.join(out_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics_dict, f, indent=2, default=str)

    if plot:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(equity_curve.index, equity_curve.values, color="tab:blue")
            ax.set_title(f"Equity curve — {label}")
            ax.set_xlabel("Time (UTC)")
            ax.set_ylabel("Equity ($)")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            png_path = os.path.join(out_dir, "equity.png")
            fig.savefig(png_path, dpi=120)
            logging.getLogger(__name__).info("Wrote %s", png_path)
        except ImportError:
            logging.getLogger(__name__).warning("matplotlib not available; skipping --plot")


def main(argv: list[str] | None = None) -> int:
    logging_config.setup_logging()
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    df, label = _load_data(args)
    if df.empty:
        print("No OHLCV data loaded; aborting.", file=sys.stderr)
        return 2

    settings = BacktestSettings(
        initial_capital=args.initial_capital,
        leverage=args.leverage,
        position_size_pct=args.position_size_pct,
        max_positions=args.max_positions,
        taker_fee_pct=args.taker_fee_pct,
        slippage_bps=args.slippage_bps,
        funding_bps_per_8h=args.funding_bps_per_8h,
        allow_long=not args.no_long,
        allow_short=not args.no_short,
        htf_filter_ma=args.htf_filter_ma,
        warmup_bars=args.warmup_bars,
    )

    result = run_backtest(df, settings, symbol=label)
    metrics = summarize(result.equity_curve, result.trades)
    title = (
        f"Backtest report — {label}"
        f" ({pd.Timestamp(df['timestamp'].iloc[0]).date()} → "
        f"{pd.Timestamp(df['timestamp'].iloc[-1]).date()})"
    )
    print(format_report(metrics, title=title))

    if args.out_dir:
        _save_outputs(
            args.out_dir,
            label,
            result.equity_curve,
            result.trades,
            metrics.as_dict(),
            args.plot,
        )

    # Print a UTC-ts run footer to make logs reproducible.
    print(f"\nRun finished at {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
