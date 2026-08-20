from pydantic import BaseModel


class Item(BaseModel):
    id: int
    ime: str
    zaloga: int
    qr_code: str


class ScanRequest(BaseModel):
    qr_code: str


class DeductRequest(BaseModel):
    qr_code: str
    kolicina: int