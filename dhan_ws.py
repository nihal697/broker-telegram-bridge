"""Backward compat shim — Dhan adapter now lives in brokers/dhan.py."""
from brokers.dhan import run_forever  # noqa: F401

__all__ = ["run_forever"]
