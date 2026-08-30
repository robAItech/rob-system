"""fleet_probe — core domain logic.

Minimalen modul: implementira osnovno aritmetično funkcijo `add`.
"""


def add(a: int | float, b: int | float) -> int | float:
    """Vrni vsoto `a + b`.

    Args:
        a: prvi operand (int ali float).
        b: drugi operand (int ali float).

    Returns:
        Vsota operandov.
    """
    return a + b
