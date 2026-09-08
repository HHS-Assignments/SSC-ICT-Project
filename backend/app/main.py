from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", str(ROOT.parent / "ssc_ict.sqlite3"))
CATALOG_PATH = ROOT / "catalog.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrderCreate(BaseModel):
    service_id: int
    quantity: int = Field(default=1, ge=1, le=50)
    custom_name: Optional[str] = Field(default=None, max_length=120)
    variant: Optional[str] = Field(default=None, max_length=80)
    delivery_method: Optional[str] = Field(default=None, pattern="^(home|office)$")
    justification: Optional[str] = Field(default=None, max_length=500)
    agreement_accepted: bool = False
    privacy_notes: Optional[str] = Field(default=None, max_length=500)


class RejectPayload(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','manager','admin')),
                    manager_id INTEGER NULL REFERENCES users(id),
                    has_dwo_basis INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    tariff_cents INTEGER NULL,
                    unit TEXT NOT NULL,
                    delivery_time TEXT NULL,
                    unique_name_required INTEGER NOT NULL DEFAULT 0,
                    requires_dwo_basis INTEGER NOT NULL DEFAULT 0,
                    requires_agreement INTEGER NOT NULL DEFAULT 0,
                    requirements_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    service_id INTEGER NOT NULL REFERENCES services(id),
                    status TEXT NOT NULL CHECK(status IN (
                        'pending_manager_approval','approved','delivered','rejected','returned'
                    )),
                    quantity INTEGER NOT NULL,
                    custom_name TEXT NULL,
                    variant TEXT NULL,
                    delivery_method TEXT NULL,
                    justification TEXT NULL,
                    agreement_accepted INTEGER NOT NULL DEFAULT 0,
                    privacy_notes TEXT NULL,
                    approved_by INTEGER NULL REFERENCES users(id),
                    rejection_reason TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
                CREATE INDEX IF NOT EXISTS idx_users_manager_id ON users(manager_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_custom_name
                    ON orders(custom_name)
                    WHERE custom_name IS NOT NULL AND status != 'rejected' AND status != 'returned';
                """
            )
            self._seed_users(conn)
            self._seed_catalog(conn)

    def _seed_users(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if existing:
            return
        conn.execute(
            "INSERT INTO users(email, name, role, manager_id, has_dwo_basis) VALUES (?,?,?,?,?)",
            ("h.vandermeer@example.gov", "Henk van der Meer", "manager", None, 1),
        )
        henk_id = conn.execute("SELECT id FROM users WHERE email=?", ("h.vandermeer@example.gov",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO users(email, name, role, manager_id, has_dwo_basis) VALUES (?,?,?,?,?)",
            ("lotte.devries@example.gov", "Lotte de Vries", "user", henk_id, 1),
        )
        conn.execute(
            "INSERT INTO users(email, name, role, manager_id, has_dwo_basis) VALUES (?,?,?,?,?)",
            ("mira.vandenberg@example.gov", "Mira van den Berg", "user", henk_id, 1),
        )
        conn.execute(
            "INSERT INTO users(email, name, role, manager_id, has_dwo_basis) VALUES (?,?,?,?,?)",
            ("daan.koster@example.gov", "Daan Koster", "admin", None, 1),
        )
        conn.execute(
            "INSERT INTO users(email, name, role, manager_id, has_dwo_basis) VALUES (?,?,?,?,?)",
            ("no.basis@example.gov", "Gebruiker Zonder DWO Basis", "user", henk_id, 0),
        )

    def _seed_catalog(self, conn: sqlite3.Connection) -> None:
        for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8")):
            conn.execute(
                """
                INSERT INTO services (
                    category, name, description, tariff_cents, unit, delivery_time,
                    unique_name_required, requires_dwo_basis, requires_agreement, requirements_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    category=excluded.category,
                    description=excluded.description,
                    tariff_cents=excluded.tariff_cents,
                    unit=excluded.unit,
                    delivery_time=excluded.delivery_time,
                    unique_name_required=excluded.unique_name_required,
                    requires_dwo_basis=excluded.requires_dwo_basis,
                    requires_agreement=excluded.requires_agreement,
                    requirements_json=excluded.requirements_json
                """,
                (
                    item["category"],
                    item["name"],
                    item["description"],
                    item["tariff_cents"],
                    item["unit"],
                    item["delivery_time"],
                    int(item["unique_name_required"]),
                    int(item["requires_dwo_basis"]),
                    int(item["requires_agreement"]),
                    json.dumps(item["requirements"], ensure_ascii=False),
                ),
            )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if "requirements_json" in data:
        data["requirements"] = json.loads(data.pop("requirements_json") or "[]")
    for key in ("unique_name_required", "requires_dwo_basis", "requires_agreement", "agreement_accepted", "has_dwo_basis"):
        if key in data:
            data[key] = bool(data[key])
    return data


def public_order(row: sqlite3.Row, include_privacy: bool) -> dict[str, Any]:
    data = row_to_dict(row) or {}
    if not include_privacy:
        data.pop("privacy_notes", None)
    return data


def create_app(db_path: str = DEFAULT_DB_PATH) -> FastAPI:
    database = Database(db_path)
    database.init()

    app = FastAPI(
        title="SSC-ICT Self Service Portal API",
        version="1.0.0",
        description="Self Service Portal/Webshop API based on the SSC-ICT factsheet assignment.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_conn():
        with database.connect() as conn:
            yield conn

    def current_user(
        conn: sqlite3.Connection = Depends(get_conn),
        x_user_email: str = Header(default="lotte.devries@example.gov"),
    ) -> dict[str, Any]:
        user = conn.execute("SELECT * FROM users WHERE email=?", (x_user_email,)).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
        return row_to_dict(user) or {}

    def require_manager(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] not in ("manager", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager role required")
        return user

    def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
        return user

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/me")
    def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return user

    @app.get("/api/users")
    def users(conn: sqlite3.Connection = Depends(get_conn), _: dict[str, Any] = Depends(require_admin)):
        rows = conn.execute("SELECT id, email, name, role, manager_id, has_dwo_basis FROM users ORDER BY name").fetchall()
        return [row_to_dict(r) for r in rows]

    @app.get("/api/services")
    def services(
        conn: sqlite3.Connection = Depends(get_conn),
        q: str | None = Query(default=None),
        category: str | None = Query(default=None),
    ):
        sql = "SELECT * FROM services WHERE 1=1"
        params: list[Any] = []
        if q:
            sql += " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"
            params += [f"%{q.lower()}%", f"%{q.lower()}%"]
        if category:
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY category, name"
        rows = conn.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]

    @app.post("/api/orders", status_code=status.HTTP_201_CREATED)
    def create_order(
        payload: OrderCreate,
        conn: sqlite3.Connection = Depends(get_conn),
        user: dict[str, Any] = Depends(current_user),
    ):
        service = conn.execute("SELECT * FROM services WHERE id=?", (payload.service_id,)).fetchone()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        service_dict = row_to_dict(service) or {}

        custom_name = payload.custom_name.strip() if payload.custom_name else None
        if service_dict["unique_name_required"] and not custom_name:
            raise HTTPException(status_code=422, detail="This service requires a unique name")
        if custom_name:
            existing = conn.execute(
                "SELECT id FROM orders WHERE LOWER(custom_name)=LOWER(?) AND status NOT IN ('rejected','returned')",
                (custom_name,),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="The requested name is already in use")

        if service_dict["requires_dwo_basis"] and not user["has_dwo_basis"]:
            raise HTTPException(status_code=422, detail="This service can only be requested with DWO Basis")

        if service_dict["requires_agreement"]:
            if payload.delivery_method not in ("home", "office"):
                raise HTTPException(status_code=422, detail="Hardware requires delivery at home or office")
            if not payload.agreement_accepted:
                raise HTTPException(status_code=422, detail="User agreement must be accepted before ordering")

        # First Time Right: validation is complete before inserting the order.
        needs_approval = (service_dict["tariff_cents"] or 0) >= 30000
        order_status = "pending_manager_approval" if needs_approval else "delivered"
        now = utc_now()
        cur = conn.execute(
            """
            INSERT INTO orders (
                user_id, service_id, status, quantity, custom_name, variant, delivery_method,
                justification, agreement_accepted, privacy_notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload.service_id,
                order_status,
                payload.quantity,
                custom_name,
                payload.variant,
                payload.delivery_method,
                payload.justification,
                int(payload.agreement_accepted),
                payload.privacy_notes,
                now,
                now,
            ),
        )
        order = conn.execute(
            """
            SELECT o.*, s.name AS service_name, s.category AS service_category, s.tariff_cents AS service_tariff_cents,
                   u.name AS user_name, u.email AS user_email
            FROM orders o
            JOIN services s ON s.id = o.service_id
            JOIN users u ON u.id = o.user_id
            WHERE o.id=?
            """,
            (cur.lastrowid,),
        ).fetchone()
        return public_order(order, include_privacy=True)

    @app.get("/api/orders/my")
    def my_orders(conn: sqlite3.Connection = Depends(get_conn), user: dict[str, Any] = Depends(current_user)):
        rows = conn.execute(
            """
            SELECT o.*, s.name AS service_name, s.category AS service_category, s.tariff_cents AS service_tariff_cents,
                   u.name AS user_name, u.email AS user_email
            FROM orders o
            JOIN services s ON s.id = o.service_id
            JOIN users u ON u.id = o.user_id
            WHERE o.user_id=?
            ORDER BY o.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        return [public_order(r, include_privacy=True) for r in rows]

    @app.post("/api/orders/{order_id}/return")
    def return_order(order_id: int, conn: sqlite3.Connection = Depends(get_conn), user: dict[str, Any] = Depends(current_user)):
        order = conn.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user["id"])).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["status"] not in ("delivered", "approved"):
            raise HTTPException(status_code=409, detail="Only approved or delivered services can be returned")
        conn.execute("UPDATE orders SET status='returned', updated_at=? WHERE id=?", (utc_now(), order_id))
        return {"status": "returned", "order_id": order_id}

    @app.get("/api/manager/orders")
    def manager_orders(
        conn: sqlite3.Connection = Depends(get_conn),
        manager: dict[str, Any] = Depends(require_manager),
    ):
        if manager["role"] == "admin":
            rows = conn.execute(
                """
                SELECT o.*, s.name AS service_name, s.category AS service_category, s.tariff_cents AS service_tariff_cents,
                       u.name AS user_name, u.email AS user_email
                FROM orders o
                JOIN services s ON s.id = o.service_id
                JOIN users u ON u.id = o.user_id
                ORDER BY o.created_at DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT o.*, s.name AS service_name, s.category AS service_category, s.tariff_cents AS service_tariff_cents,
                       u.name AS user_name, u.email AS user_email
                FROM orders o
                JOIN services s ON s.id = o.service_id
                JOIN users u ON u.id = o.user_id
                WHERE u.manager_id=?
                ORDER BY o.created_at DESC
                """,
                (manager["id"],),
            ).fetchall()
        # Privacy notes intentionally hidden from managers per assignment.
        return [public_order(r, include_privacy=False) for r in rows]

    @app.post("/api/manager/orders/{order_id}/approve")
    def approve_order(order_id: int, conn: sqlite3.Connection = Depends(get_conn), manager: dict[str, Any] = Depends(require_manager)):
        row = conn.execute(
            """
            SELECT o.*, u.manager_id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id=?
            """,
            (order_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        if manager["role"] != "admin" and row["manager_id"] != manager["id"]:
            raise HTTPException(status_code=403, detail="Order is outside your team")
        if row["status"] != "pending_manager_approval":
            raise HTTPException(status_code=409, detail="Only pending orders can be approved")
        conn.execute(
            "UPDATE orders SET status='approved', approved_by=?, updated_at=? WHERE id=?",
            (manager["id"], utc_now(), order_id),
        )
        return {"status": "approved", "order_id": order_id}

    @app.post("/api/manager/orders/{order_id}/reject")
    def reject_order(
        order_id: int,
        payload: RejectPayload,
        conn: sqlite3.Connection = Depends(get_conn),
        manager: dict[str, Any] = Depends(require_manager),
    ):
        row = conn.execute(
            """
            SELECT o.*, u.manager_id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id=?
            """,
            (order_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        if manager["role"] != "admin" and row["manager_id"] != manager["id"]:
            raise HTTPException(status_code=403, detail="Order is outside your team")
        if row["status"] != "pending_manager_approval":
            raise HTTPException(status_code=409, detail="Only pending orders can be rejected")
        conn.execute(
            "UPDATE orders SET status='rejected', rejection_reason=?, approved_by=?, updated_at=? WHERE id=?",
            (payload.reason, manager["id"], utc_now(), order_id),
        )
        return {"status": "rejected", "order_id": order_id}

    @app.get("/api/admin/orders")
    def admin_orders(conn: sqlite3.Connection = Depends(get_conn), _: dict[str, Any] = Depends(require_admin)):
        rows = conn.execute(
            """
            SELECT o.*, s.name AS service_name, s.category AS service_category, s.tariff_cents AS service_tariff_cents,
                   u.name AS user_name, u.email AS user_email
            FROM orders o
            JOIN services s ON s.id = o.service_id
            JOIN users u ON u.id = o.user_id
            ORDER BY o.created_at DESC
            """
        ).fetchall()
        return [public_order(r, include_privacy=True) for r in rows]

    return app


app = create_app()
