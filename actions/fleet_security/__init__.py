"""fleet_security — pasivno jedro: inventar + posture + CRA + remediacija.

Podmoduli:
- schemas      — Pydantic V2 modeli (strict input, brez LLM)
- store        — SQLite persistence (stdlib, WAL)
- discovery    — pasivni collector + ingest + heartbeat
- posture      — scoring, eskalacija, regression
- compliance   — CRA report (Markdown/JSON)
- remediation  — config/network PR (firmware report-only, brez auto-merge)
- main         — FastAPI vmesnik
- cli          — CLI vmesnik
"""
