"""Pytest testi za actions/q3_report modul."""

import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from q3_report import default_data, generate_q3_report, render_report  # noqa: E402
from q3_report.schemas import Q3Metric, Q3ReportData  # noqa: E402


def test_default_data_valid():
    data = default_data()
    assert data.revenue >= 0
    assert data.expenses >= 0
    assert data.profit == data.revenue - data.expenses


def test_render_contains_sections():
    md = render_report(default_data())
    assert md.startswith("# ")
    assert "## Analiza" in md
    assert "## Povzetek" in md


def test_render_contains_values():
    data = Q3ReportData(quarter="Q3 2025", revenue=1000, expenses=400, customers=5)
    md = render_report(data)
    assert "Q3 2025" in md
    assert "1000" in md
    assert "600" in md  # izračunan dobiček
    assert "## Analiza" in md
    assert "## Povzetek" in md


def test_negative_revenue_rejected():
    with pytest.raises(ValidationError):
        Q3ReportData(quarter="Q3", revenue=-1, expenses=1)


def test_blank_quarter_rejected():
    with pytest.raises(ValidationError):
        Q3ReportData(quarter="   ", revenue=1, expenses=1)


def test_profit_auto_computed():
    data = Q3ReportData(quarter="Q3", revenue=100, expenses=30)
    assert data.profit == 70


def test_explicit_profit_kept():
    data = Q3ReportData(quarter="Q3", revenue=100, expenses=30, profit=42)
    assert data.profit == 42


def test_metric_blank_name_rejected():
    with pytest.raises(ValidationError):
        Q3Metric(name="  ", value=1)


def test_generate_async():
    md = asyncio.run(generate_q3_report())
    assert md.startswith("# ")
    assert "## Analiza" in md
    assert "## Povzetek" in md


def test_report_file_exists_with_real_content():
    path = Path(__file__).resolve().parent / "report.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# ")
    assert "## Analiza" in content
    assert "## Povzetek" in content
    assert "TODO" not in content
    assert "PLACEHOLDER" not in content.upper()
