from typing import Dict, Optional
from actions.warehouse_inventory.schemas import Item


class InventoryManager:
    def __init__(self):
        # Mock baza podatkov
        self._items: Dict[str, Item] = {
            "QR-VIJAKI-M8": Item(
                id=1,
                ime="Vijaki M8",
                zaloga=100,
                qr_code="QR-VIJAKI-M8"
            ),
            "QR-MATICE-M8": Item(
                id=2,
                ime="Matice M8",
                zaloga=50,
                qr_code="QR-MATICE-M8"
            ),
            "QR-SVORNIKI-10": Item(
                id=3,
                ime="Svorniki 10mm",
                zaloga=30,
                qr_code="QR-SVORNIKI-10"
            )
        }

    def scan_item(self, qr_code: str) -> Optional[Item]:
        """Skenira artikel in vrne njegove podatke."""
        return self._items.get(qr_code)

    def deduct_stock(self, qr_code: str, kolicina: int) -> Item:
        """Odšteje zalogo za artikel. Vrne napako, če ni dovolj zaloge."""
        item = self._items.get(qr_code)
        if not item:
            raise ValueError(f"Artikel s QR kodo '{qr_code}' ne obstaja.")

        if kolicina <= 0:
            raise ValueError("Količina mora biti pozitivno število.")

        if item.zaloga < kolicina:
            raise ValueError(
                f"Premalo zaloge za artikel '{item.ime}'. "
                f"Na voljo: {item.zaloga}, zahtevano: {kolicina}."
            )

        item.zaloga -= kolicina
        return item