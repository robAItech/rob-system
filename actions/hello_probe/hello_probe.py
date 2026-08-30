"""hello_probe — jedro domenske logike.

Preprost modul s funkcijo ``greet``, ki vrne pozdrav za podano ime.
"""


def greet(ime: str) -> str:
    """Vrne pozdravni niz za podano ime.

    Args:
        ime: Ime osebe, ki jo pozdravljamo.

    Returns:
        Niz oblike ``"Pozdrav, <ime>"``.
    """
    return "Pozdrav, " + ime