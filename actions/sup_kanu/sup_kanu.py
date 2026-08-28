"""Core domain logic za modul sup_kanu.

Arhitekturna usmeritev:
  - logika: Čista async logika -> `build_site_html` in `get_site_content` sta
    async vhodni točki, ki iz Pydantic sheme (SiteContent) oziroma iz
    datoteke index.html vrneta celotno vsebino spletne strani.
  - Izdelek: index.html v actions/sup_kanu/ (moderna, mobilno odzivna
    spletna stran podjetja SUP Kanu Ljubljanica z navigacijo).
"""

from pathlib import Path

from .schemas import ContactInfo, OpeningHours, PriceEntry, PriceRow, SiteContent

MODULE_DIR = Path(__file__).resolve().parent
HTML_FILENAME = "index.html"
HTML_PATH = MODULE_DIR / HTML_FILENAME


def default_site_content() -> SiteContent:
    """Privzeta vsebina spletne strani SUP Kanu Ljubljanica."""
    return SiteContent(
        title="SUP Kanu Ljubljanica – izposoja SUP desk in kanujev na Ljubljanici",
        about=(
            "SUP Kanu Ljubljanica je domača ekipa, ki domačinom in obiskovalcem že več kot "
            "deset let omogoča, da Ljubljano doživijo iz povsem druge perspektive — z reke. "
            "Naš ponton leži ob Gallusovem nabrežju, v srcu mesta. Za vsakega gosta imamo "
            "pregledano opremo, rešilne jopiče in prijazen uvodni tečaj, da se na vodi počutite "
            "varno že od prve minute."
        ),
        offers=[
            "Izposoja SUP desk – stabilne deske za vse ravni znanja z veslom in rešilnim jopičem.",
            "Izposoja kanujev – dvosedežni in trisedežni kanuji za raziskovanje Ljubljanice.",
            "Najem in vodeni izleti – dolgoročni najem, skupinski izleti in team building ob sončnem zahodu.",
        ],
        prices=[
            PriceRow(
                label="SUP deska",
                prices=[
                    PriceEntry(duration="1h", price_eur=12.0),
                    PriceEntry(duration="2h", price_eur=20.0),
                    PriceEntry(duration="dan", price_eur=35.0),
                ],
            ),
            PriceRow(
                label="Kanu (2 osebi)",
                prices=[
                    PriceEntry(duration="1h", price_eur=15.0),
                    PriceEntry(duration="2h", price_eur=25.0),
                    PriceEntry(duration="dan", price_eur=45.0),
                ],
            ),
            PriceRow(
                label="Kanu (3 osebe)",
                prices=[
                    PriceEntry(duration="1h", price_eur=18.0),
                    PriceEntry(duration="2h", price_eur=30.0),
                    PriceEntry(duration="dan", price_eur=55.0),
                ],
            ),
        ],
        contact=ContactInfo(
            address="Gallusovo nabrežje 27, 1000 Ljubljana",
            phone="+386 40 123 456",
            email="info@supkanu-ljubljanica.si",
        ),
        opening_hours=[
            OpeningHours(day="Ponedeljek – petek", hours="10:00 – 20:00"),
            OpeningHours(day="Sobota", hours="09:00 – 21:00"),
            OpeningHours(day="Nedelja in prazniki", hours="09:00 – 20:00"),
        ],
        gallery=[
            "SUP deske pripravljene ob nabrežju",
            "Kanu na mirni Ljubljanici",
            "Vodeni izlet ob sončnem zahodu",
            "Začetniški tečaj SUP-a",
            "Družinski izlet po reki",
            "Varnostna oprema in rešilni jopiči",
        ],
    )


async def get_site_content() -> SiteContent:
    """Async vhodna točka: vrne strukturirano vsebino strani (Pydantic shema)."""
    return default_site_content()


async def build_site_html() -> str:
    """Async vhodna točka: vrne celotno HTML vsebino iz datoteke index.html.

    Raises:
        FileNotFoundError: če datoteka index.html v actions/sup_kanu/ ne obstaja.
    """
    if not HTML_PATH.exists():
        raise FileNotFoundError(
            f"Manjka datoteka {HTML_FILENAME} v actions/sup_kanu/. "
            "Spletno stran je treba najprej generirati."
        )
    return HTML_PATH.read_text(encoding="utf-8")
