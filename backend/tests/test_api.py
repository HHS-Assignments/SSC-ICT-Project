import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def client():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    app = create_app(tmp.name)
    return TestClient(app), Path(tmp.name)


def test_catalog_contains_factsheet_services_and_prices():
    c, db = client()
    try:
        response = c.get("/api/services")
        assert response.status_code == 200
        services = response.json()
        assert len(services) >= 21
        visio = next(s for s in services if s["name"] == "Microsoft Visio Standaard")
        assert visio["tariff_cents"] == 22500
        smartphone = next(s for s in services if s["name"] == "Managed Smartphone premium")
        assert smartphone["delivery_time"] == "5 werkdagen"
    finally:
        db.unlink(missing_ok=True)


def test_user_can_only_see_own_orders():
    c, db = client()
    try:
        services = c.get("/api/services").json()
        emailalias = next(s for s in services if s["name"] == "Emailalias")

        lotte_headers = {"X-User-Email": "lotte.devries@example.gov"}
        mira_headers = {"X-User-Email": "mira.vandenberg@example.gov"}

        created = c.post(
            "/api/orders",
            headers=lotte_headers,
            json={"service_id": emailalias["id"], "custom_name": "lotte.alias"},
        )
        assert created.status_code == 201

        lotte_orders = c.get("/api/orders/my", headers=lotte_headers).json()
        mira_orders = c.get("/api/orders/my", headers=mira_headers).json()

        assert len(lotte_orders) == 1
        assert lotte_orders[0]["custom_name"] == "lotte.alias"
        assert mira_orders == []
    finally:
        db.unlink(missing_ok=True)


def test_unique_name_validation_supports_first_time_right():
    c, db = client()
    try:
        teams = next(s for s in c.get("/api/services").json() if s["name"] == "Teams")
        headers = {"X-User-Email": "lotte.devries@example.gov"}

        first = c.post(
            "/api/orders",
            headers=headers,
            json={"service_id": teams["id"], "custom_name": "Programma-Duurzaamheid", "justification": "Projectteam"},
        )
        assert first.status_code == 201

        duplicate = c.post(
            "/api/orders",
            headers=headers,
            json={"service_id": teams["id"], "custom_name": "Programma-Duurzaamheid"},
        )
        assert duplicate.status_code == 409
    finally:
        db.unlink(missing_ok=True)


def test_hardware_requires_delivery_and_signed_agreement():
    c, db = client()
    try:
        laptop = next(s for s in c.get("/api/services").json() if s["name"] == "Managed Laptop standaard")
        headers = {"X-User-Email": "lotte.devries@example.gov"}

        missing_agreement = c.post("/api/orders", headers=headers, json={"service_id": laptop["id"]})
        assert missing_agreement.status_code == 422

        ok = c.post(
            "/api/orders",
            headers=headers,
            json={
                "service_id": laptop["id"],
                "delivery_method": "office",
                "agreement_accepted": True,
                "variant": "Klein 13 inch",
            },
        )
        assert ok.status_code == 201
        assert ok.json()["status"] == "pending_manager_approval"
    finally:
        db.unlink(missing_ok=True)


def test_manager_approval_and_privacy_filter():
    c, db = client()
    try:
        spss = next(s for s in c.get("/api/services").json() if s["name"] == "SPSS")
        user_headers = {"X-User-Email": "lotte.devries@example.gov"}
        manager_headers = {"X-User-Email": "h.vandermeer@example.gov"}

        created = c.post(
            "/api/orders",
            headers=user_headers,
            json={
                "service_id": spss["id"],
                "justification": "Data-analyse beleid",
                "privacy_notes": "Contains confidential personnel context",
            },
        )
        assert created.status_code == 201
        order_id = created.json()["id"]

        manager_list = c.get("/api/manager/orders", headers=manager_headers)
        assert manager_list.status_code == 200
        assert "privacy_notes" not in manager_list.json()[0]

        approved = c.post(f"/api/manager/orders/{order_id}/approve", headers=manager_headers)
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
    finally:
        db.unlink(missing_ok=True)


def test_dwo_services_require_dwo_basis():
    c, db = client()
    try:
        dwo = next(s for s in c.get("/api/services").json() if s["name"] == "Digitale Werkomgeving Online Ontwikkel/Test")
        response = c.post(
            "/api/orders",
            headers={"X-User-Email": "no.basis@example.gov"},
            json={"service_id": dwo["id"]},
        )
        assert response.status_code == 422
        assert "DWO Basis" in response.json()["detail"]
    finally:
        db.unlink(missing_ok=True)
