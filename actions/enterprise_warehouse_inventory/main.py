from fastapi import FastAPI, HTTPException
from actions.enterprise_warehouse_inventory.enterprise_warehouse_inventory import InventoryManager
from actions.enterprise_warehouse_inventory.schemas import Item, ScanRequest, DeductRequest

app = FastAPI()
inventory_manager = InventoryManager()


@app.post("/inventory/scan", response_model=Item)
def scan_item(request: ScanRequest):
    """Skenira artikel in vrne njegove podatke."""
    item = inventory_manager.scan_item(request.qr_code)
    if not item:
        raise HTTPException(status_code=404, detail=f"Artikel s QR kodo '{request.qr_code}' ne obstaja.")
    return item


@app.post("/inventory/deduct", response_model=Item)
def deduct_stock(request: DeductRequest):
    """Odšteje zalogo in vrne novo stanje."""
    try:
        item = inventory_manager.deduct_stock(request.qr_code, request.kolicina)
        return item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))