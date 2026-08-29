"""Jedrna domena — izdelava Markdown poročila o rezultatih Q3.

Vsebuje analizo (prihodki, stroški, dobiček, KPI) in povzetek.
"""

from __future__ import annotations

from typing import Optional

from .schemas import Q3Metric, Q3ReportData

DEFAULT_TITLE = "Poročilo o rezultatih Q3"


def _format_value(value: float) -> str:
    """Oblikuj številko: cela števila brez decimalk, ostala z največ 2 decimalkama."""
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def default_data() -> Q3ReportData:
    """Privzeti (referenčni) podatki za Q3 poročilo."""
    return Q3ReportData(
        quarter="Q3 2025",
        revenue=1_250_000,
        expenses=980_000,
        customers=1_240,
        metrics=[
            Q3Metric(name="NPS", value=72),
            Q3Metric(name="Stopnja konverzije", value=4.8, unit="%"),
        ],
    )


def render_report(data: Q3ReportData) -> str:
    """Sestavi Markdown poročilo iz podatkov: naslov, analiza, povzetek."""
    profit = data.profit if data.profit is not None else data.revenue - data.expenses
    margin = (profit / data.revenue * 100) if data.revenue > 0 else 0.0

    lines = [f"# {DEFAULT_TITLE} ({data.quarter})", ""]
    lines.append("## Analiza")
    lines.append("")
    lines.append(f"- Prihodki: **{_format_value(data.revenue)}**")
    lines.append(f"- Stroški: **{_format_value(data.expenses)}**")
    lines.append(f"- Dobiček: **{_format_value(profit)}**")
    lines.append(f"- Marža: **{_format_value(margin)} %**")
    lines.append(f"- Aktivne stranke: **{data.customers}**")
    if data.metrics:
        lines.append("")
        lines.append("Ključni KPI:")
        for m in data.metrics:
            unit = f" {m.unit}" if m.unit else ""
            lines.append(f"  - {m.name}: {_format_value(m.value)}{unit}")
    lines.append("")
    lines.append("## Povzetek")
    lines.append("")
    lines.append(
        f"V četrtletju {data.quarter} smo dosegli prihodke v višini "
        f"{_format_value(data.revenue)} ob stroških {_format_value(data.expenses)}, "
        f"kar pomeni {_format_value(profit)} dobička ({_format_value(margin)} % marža). "
        f"Baza strank je narasla na {data.customers}."
    )
    lines.append("")
    return "\n".join(lines)


async def generate_q3_report(data: Optional[Q3ReportData] = None) -> str:
    """Čista async vhodna točka — vrne celotno Markdown poročilo o Q3."""
    if data is None:
        data = default_data()
    return render_report(data)