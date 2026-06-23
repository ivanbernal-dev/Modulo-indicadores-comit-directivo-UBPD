from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import load_settings
from app.database import Database
from app.services import UserService


def ensure_user(connection, username: str, full_name: str, role: str, password: str):
    existing = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return existing
    UserService.create(connection, None, {
        "username": username,
        "full_name": full_name,
        "email": f"{username}@demo.ubpd.local",
        "password": password,
        "role": role,
    })
    return connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def main():
    settings = load_settings()
    database = Database(settings.db_path)
    database.initialize()
    with database.transaction() as connection:
        admin = ensure_user(
            connection,
            os.getenv("UBPD_ADMIN_USER", "admin"),
            "Administrador UBPD",
            "ADMIN",
            os.getenv("UBPD_ADMIN_PASSWORD", "ChangeMe2026!"),
        )
        ensure_user(connection, "cargador.demo", "Usuario Cargador Demo", "CARGADOR", "CargaDemo2026!")
        ensure_user(connection, "oap.demo", "Profesional OAP Demo", "OAP", "OapDemo2026!")
        print(f"Base inicializada: {settings.db_path}")
        print(f"Administrador: {admin['username']}")
        print("Cambie todas las contraseñas de demostración antes de publicar el servicio.")


if __name__ == "__main__":
    main()
