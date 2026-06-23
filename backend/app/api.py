from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .database import Database
from .security import create_session, resolve_session, revoke_session, verify_password
from .services import (
    CaptureService,
    CatalogService,
    DomainError,
    OapService,
    PublicService,
    TemplateService,
    UserService,
    audit,
    require_role,
)


def _first(query: dict, key: str, default=None):
    values = query.get(key)
    return values[0] if values else default


class ApiHandler(BaseHTTPRequestHandler):
    database: Database
    cors_origin = "http://127.0.0.1:4173"
    session_hours = 8
    server_version = "UBPDIndicadores/0.1"

    def log_message(self, fmt, *args):
        print(f"[API] {self.address_string()} - {fmt % args}")

    def _send(self, status: int, payload=None):
        body = json.dumps(payload if payload is not None else {}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self.cors_origin)
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DomainError("El cuerpo de la solicitud no es JSON válido") from exc

    def _token(self) -> str | None:
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            return authorization[7:].strip()
        return None

    def _user(self, connection, required=True):
        token = self._token()
        user = resolve_session(connection, token) if token else None
        if required and not user:
            raise DomainError("Sesión inválida o vencida", 401)
        return user

    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path, query = parsed.path.rstrip("/") or "/", parse_qs(parsed.query)
        payload = self._body() if method in {"POST", "PUT", "PATCH"} else {}
        with self.database.transaction() as connection:
            if method == "GET" and path == "/health":
                return 200, {"status": "ok", "service": "ubpd-indicadores-backend"}

            if method == "POST" and path == "/api/auth/login":
                user = connection.execute(
                    "SELECT * FROM users WHERE username = ? AND active = 1",
                    (payload.get("username", ""),),
                ).fetchone()
                if not user or not verify_password(payload.get("password", ""), user["password_hash"]):
                    raise DomainError("Usuario o contraseña incorrectos", 401)
                token = create_session(connection, user["id"], self.session_hours)
                audit(connection, user["id"], "LOGIN", "SESSION", None)
                return 200, {"token": token, "user": {
                    "id": user["id"], "username": user["username"],
                    "full_name": user["full_name"], "role": user["role"],
                }}

            if method == "POST" and path == "/api/auth/logout":
                user = self._user(connection)
                revoke_session(connection, self._token())
                audit(connection, user["id"], "LOGOUT", "SESSION", None)
                return 200, {"message": "Sesión cerrada"}

            if method == "GET" and path == "/api/auth/me":
                user = self._user(connection)
                dependencies = [dict(row) for row in connection.execute(
                    """SELECT d.id, d.codigo, d.nombre FROM dependencias d
                       JOIN user_dependencias ud ON ud.dependencia_id = d.id
                       WHERE ud.user_id = ? ORDER BY d.nombre""", (user["id"],)
                ).fetchall()]
                return 200, {"id": user["id"], "username": user["username"],
                             "full_name": user["full_name"], "email": user["email"],
                             "role": user["role"], "dependencias": dependencies}

            if method == "GET" and path == "/api/catalog/lines":
                self._user(connection)
                return 200, CatalogService.list_lines(connection)

            if method == "GET" and path == "/api/catalog/dependencies":
                self._user(connection)
                line_id = _first(query, "line_id")
                year = _first(query, "year")
                return 200, CatalogService.list_dependencies(
                    connection, int(line_id) if line_id else None, int(year) if year else None
                )

            if method == "GET" and path == "/api/admin/users":
                return 200, UserService.list(connection, self._user(connection))

            if method == "POST" and path == "/api/admin/users":
                return 201, UserService.create(connection, self._user(connection), payload)

            if method == "POST" and path == "/api/admin/periods":
                user = self._user(connection)
                require_role(user, "ADMIN")
                try:
                    cursor = connection.execute(
                        """INSERT INTO reporting_periods
                           (vigencia, mes, fecha_apertura, fecha_cierre, estado)
                           VALUES (?, ?, ?, ?, ?)""",
                        (int(payload["vigencia"]), int(payload["mes"]), payload.get("fecha_apertura"),
                         payload.get("fecha_cierre"), payload.get("estado", "ABIERTO").upper()),
                    )
                except Exception as exc:
                    raise DomainError("El periodo es inválido o ya existe") from exc
                audit(connection, user["id"], "CREATE", "REPORTING_PERIOD", cursor.lastrowid, payload)
                return 201, dict(connection.execute(
                    "SELECT * FROM reporting_periods WHERE id = ?", (cursor.lastrowid,)
                ).fetchone())

            if method == "GET" and path == "/api/templates":
                self._user(connection)
                year, status = _first(query, "year"), _first(query, "status")
                return 200, TemplateService.list(connection, int(year) if year else None, status)

            if method == "POST" and path == "/api/templates":
                return 201, TemplateService.create(connection, self._user(connection), payload)

            match = re.fullmatch(r"/api/templates/(\d+)", path)
            if method == "GET" and match:
                self._user(connection)
                return 200, TemplateService.get(connection, int(match.group(1)))

            match = re.fullmatch(r"/api/templates/(\d+)/variables", path)
            if method == "POST" and match:
                return 201, TemplateService.add_variable(
                    connection, self._user(connection), int(match.group(1)), payload
                )

            match = re.fullmatch(r"/api/templates/(\d+)/activate", path)
            if method == "POST" and match:
                return 200, TemplateService.activate(connection, self._user(connection), int(match.group(1)))

            if method == "GET" and path == "/api/capture/assignments":
                year = int(_first(query, "year", "2026"))
                month = int(_first(query, "month", "1"))
                return 200, CaptureService.assignments(connection, self._user(connection), year, month)

            match = re.fullmatch(r"/api/capture/reports/(\d+)/(\d{4})/(\d{1,2})", path)
            if method == "PUT" and match:
                return 200, CaptureService.save_report(
                    connection, self._user(connection), int(match.group(1)),
                    int(match.group(2)), int(match.group(3)), payload,
                )

            match = re.fullmatch(r"/api/capture/reports/(\d+)", path)
            if method == "GET" and match:
                self._user(connection)
                return 200, CaptureService.get_report(connection, int(match.group(1)))

            match = re.fullmatch(r"/api/capture/reports/(\d+)/submit", path)
            if method == "POST" and match:
                return 200, CaptureService.submit(connection, self._user(connection), int(match.group(1)))

            if method == "GET" and path == "/api/oap/reports":
                status = _first(query, "status", "ENVIADO")
                return 200, OapService.queue(connection, self._user(connection), status)

            match = re.fullmatch(r"/api/oap/reports/(\d+)/review", path)
            if method == "POST" and match:
                return 200, OapService.review(
                    connection, self._user(connection), int(match.group(1)), payload
                )

            if method == "GET" and path == "/api/public/indicators":
                year = int(_first(query, "year", "2026"))
                line_id, dependency_id = _first(query, "line_id"), _first(query, "dependency_id")
                return 200, PublicService.indicators(
                    connection, year, int(line_id) if line_id else None,
                    int(dependency_id) if dependency_id else None,
                    _first(query, "active_only", "true").lower() != "false",
                )

            raise DomainError("Ruta no encontrada", 404)

    def _handle(self, method: str):
        try:
            status, payload = self._dispatch(method)
            self._send(status, payload)
        except DomainError as exc:
            self._send(exc.status, {"error": exc.message})
        except Exception as exc:
            print(f"[ERROR] {exc!r}")
            self._send(500, {"error": "Error interno del servidor"})

    def do_OPTIONS(self):
        self._send(HTTPStatus.NO_CONTENT, {})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_PATCH(self):
        self._handle("PATCH")
