"""demo_bug — namerno pokvarjen modul za demonstracijo Zanke 1 (konsolidacija).

NAMERNA NAPAKA: ``divide`` ne preveri deljenja z nič in pusti, da Python vrže
``ZeroDivisionError``, namesto da bi vrnil ``ValueError``. Test
``test_divide_by_zero_raises_valueerror`` zato pade s specifičnim tracebackom,
ki ga konsolidator strdi v ponovno uporabljivo lekcijo.

To ni produkcijski modul — je učni vzorec, ki dokaže, da se sistem iz resnične
napake resnično nauči.
"""


def divide(a: float, b: float) -> float:
    """Deli ``a`` z ``b``.

    Ob deljenju z nič (``b == 0``) vrne ``ValueError`` s sporočilom
    'deljenje z nič ni dovoljeno', ne ``ZeroDivisionError``.
    """
    if b == 0:
        raise ValueError("deljenje z nič ni dovoljeno")
    return a / b