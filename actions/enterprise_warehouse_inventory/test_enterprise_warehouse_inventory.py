import pytest
from fastapi.testclient import TestClient
from actions.enterprise_warehouse_inventory.main import app

client = TestClient(app)


def test_uspesno_skeniranje():
    """Test uspešnega skeniranja artikla."""
    response = client.post("/inventory/scan", json={"qr_code": "QR-VIJAKI-M8"})
    assert response.status_code == 200
    data = response.json()
    assert data["qr_code"] == "QR-VIJAKI-M8"
    assert data["ime"] == "Vijaki M8"
    assert data["zaloga"] == 100


def test_uspesno_odstevanje_zaloge():
    """Test uspešnega odštevanja zaloge."""
    response = client.post("/inventory/deduct", json={"qr_code": "QR-VIJAKI-M8", "kolicina": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["qr_code"] == "QR-VIJAKI-M8"
    assert data["zaloga"] == 90


def test_skeniranje_neobstojece_kode():
    """Test skeniranja neobstoječe QR kode."""
    response = client.post("/inventory/scan", json={"qr_code": "QR-NEOBSTOJI"})
    assert response.status_code == 404
    assert "ne obstaja" in response.json()["detail"]


def test_odstevanje_prevelike_kolicine():
    """Test poskusa odštevanja prevelike količine."""
    response = client.post("/inventory/deduct", json={"qr_code": "QR-VIJAKI-M8", "kolicina": 999})
    assert response.status_code == 400
    assert "Premalo zaloge" in response.json()["detail"]


def test_odstevanje_neobstojecega_artikla():
    """Test odštevanja zaloge za neobstoječ artikel."""
    response = client.post("/inventory/deduct", json={"qr_code": "QR-NEOBSTOJI", "kolicina": 5})
    assert response.status_code == 400
    assert "ne obstaja" in response.json()["detail"]


def test_odstevanje_negativne_kolicine():
    """Test odštevanja z negativno količino."""
    response = client.post("/inventory/deduct", json={"qr_code": "QR-VIJAKI-M8", "kolicina": -5})
    assert response.status_code == 400
    assert "pozitivno" in response.json()["detail"]