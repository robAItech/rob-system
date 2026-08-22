"""Lokalna higiena: P0 bugfix kopije (fix_*) ne smejo v pytest collection.

CI teče le `tests/`, zato to ni CI-tveganje — samo prepreči, da lokalni
`pytest tests/ actions` pobere bugirane kopije (RDEČE po FAILED eval teku).
"""
import os

collect_ignore = [d for d in os.listdir(os.path.dirname(__file__)) if d.startswith("fix_")]
