"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with a compact JSON-ish line format.

    Idempotent: repeated calls only adjust the level, they do not attach
    duplicate handlers.
    """

    global _CONFIGURED
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if _CONFIGURED:
        logging.getLogger().setLevel(numeric_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""

    return logging.getLogger(name)
