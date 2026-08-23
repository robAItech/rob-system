"""normalizer.py — normalizacija niza (male črke, strnjeni presledki)."""


def normalize(text: str) -> str:
    """Normalizira niz: male črke, odstranjeni robni presledki, strnjeni presledki.

    Args:
        text: vhodni niz (mora biti str).

    Returns:
        Normaliziran niz; prazen niz za prazen vhod.

    Raises:
        TypeError: če `text` ni niz.
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize() pričakuje str, dobil {type(text).__name__}")
    return " ".join(text.lower().split())