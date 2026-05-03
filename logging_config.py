"""Centralized logging setup. Honors LOG_LEVEL from config."""

from __future__ import annotations

import logging
import os
import sys

from config import LOG_FILE, LOG_LEVEL

_DEF_FMT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_DEF_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> logging.Logger:
    """Configure root logger once. Safe to call multiple times."""
    root = logging.getLogger()
    if getattr(root, "_future_simulasi_configured", False):
        return root

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(_DEF_FMT, datefmt=_DEF_DATEFMT)

    # Console handler
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # File handler (best-effort; bot stays alive even if disk is read-only)
    try:
        log_dir = os.path.dirname(LOG_FILE) or "."
        os.makedirs(log_dir, exist_ok=True)
        bot_log = os.path.join(log_dir, "bot.log")
        fh = logging.FileHandler(bot_log)
        fh.setLevel(level)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except OSError as exc:  # pragma: no cover - depends on filesystem
        root.warning("Failed to attach file handler: %s", exc)

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    root._future_simulasi_configured = True  # type: ignore[attr-defined]
    return root
