from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from .formulas import FormulaError, evaluate_formula
from .security import hash_password


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def as_dict(row) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def audit(connection, user_id: int | None, action: str, entity_type: str, entity_id: Any, details=None):
    connection.execute(
        """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details_json)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, action, entity_type, str(entity_id) if entity_id is not None else None,
         json.dumps(details or {}, ensure_ascii=False)),
    )


def require_role(user, *roles: str) -> None:
    if user["role"] not in roles:
        raise DomainError("No tiene permisos para realizar esta acción", 403)


class UserService:
    @staticmethod
    def create(connection, actor, payload: dict) -> dict:
        if actor is not None:
            require_role(actor, "ADMIN")
        role = payload.get("role", "CARGADOR").upper()
        if role not in {"ADMIN", "CARGADOR", "OAP", "CONSULTA"}:
            raise DomainError("Rol inválido")
        try:
            cursor = connection.execute(
                """INSERT INTO users (username, full_name, email, password_hash, role)
                   VALUES (?, ?, ?, ?, ?)""",
                (payload["username"].strip(), payload["full_name"].strip(), payload.get("email"),
                 hash_password(payload["password"]), role),
            )
        except (KeyError, sqlite3.IntegrityError) as exc:
            raise DomainError("El usuario es inválido o ya existe") from exc
        user_id = cursor.lastrowid
        for dependencia_id in payload.get("dependencia_ids", []):
            connection.execute(
                "INSERT OR IGNORE INTO user_dependencias (user_id, dependencia_id) VALUES (?, ?)",
                (user_id, int(dependencia_id)),
            )
        audit(connection, actor["id"] if actor else user_id, "CREATE", "USER", user_id, {"role": role})
        return as_dict(connection.execute(
            "SELECT id, username, full_name, email, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone())

    @staticmethod
    def list(connection, actor) -> list[dict]:
        require_role(actor, "ADMIN")
        rows = connection.execute(
            "SELECT id, username, full_name, email, role, active, created_at FROM users ORDER BY full_name"
        ).fetchall()
        return [dict(row) for row in rows]


class CatalogService:
    @staticmethod
    def list_lines(connection) -> list[dict]:
        return [dict(row) for row in connection.execute(
            "SELECT id, codigo, nombre FROM lineas_estrategicas WHERE activa = 1 ORDER BY codigo"
        ).fetchall()]

    @staticmethod
    def list_dependencies(connection, line_id: int | None = None, year: int | None = None) -> list[dict]:
        if line_id:
            rows = connection.execute(
                """SELECT DISTINCT d.id, d.codigo, d.nombre
                   FROM dependencias d JOIN templates t ON t.dependencia_id = d.id
                   WHERE d.activa = 1 AND t.linea_id = ? AND (? IS NULL OR t.vigencia = ?)
                   ORDER BY d.nombre""",
                (line_id, year, year),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, codigo, nombre FROM dependencias WHERE activa = 1 ORDER BY nombre"
            ).fetchall()
        return [dict(row) for row in rows]


class TemplateService:
    @staticmethod
    def create(connection, actor, payload: dict) -> dict:
        require_role(actor, "ADMIN", "OAP")
        required = ["codigo", "vigencia", "linea_id", "dependencia_id", "nombre", "formula_expression"]
        missing = [field for field in required if payload.get(field) in (None, "")]
        if missing:
            raise DomainError(f"Faltan campos del template: {', '.join(missing)}")
        version = payload.get("version")
        if version is None:
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 next_version FROM templates WHERE codigo = ? AND vigencia = ?",
                (payload["codigo"], int(payload["vigencia"])),
            ).fetchone()["next_version"]
        source_status = payload.get("estado_indicador", "Activo")
        if source_status not in {"Activo", "Modificado", "Nuevo", "Inactivo"}:
            raise DomainError("Estado fuente del indicador inválido")
        try:
            cursor = connection.execute(
                """INSERT INTO templates (
                       codigo, vigencia, version, linea_id, dependencia_id, nombre, objetivo,
                       definicion_operativa, formula_expression, formula_display,
                       unidad_medida, periodicidad, meta_anual, fuente_informacion,
                       estado_indicador, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payload["codigo"], int(payload["vigencia"]), int(version), int(payload["linea_id"]),
                 int(payload["dependencia_id"]), payload["nombre"], payload.get("objetivo"),
                 payload.get("definicion_operativa"), payload["formula_expression"],
                 payload.get("formula_display"), payload.get("unidad_medida"),
                 payload.get("periodicidad", "Mensual"), payload.get("meta_anual"),
                 payload.get("fuente_informacion"), source_status, actor["id"]),
            )
        except sqlite3.IntegrityError as exc:
            raise DomainError("La versión del template ya existe para esa vigencia") from exc
        template_id = cursor.lastrowid
        for variable in payload.get("variables", []):
            TemplateService.add_variable(connection, actor, template_id, variable, audit_change=False)
        audit(connection, actor["id"], "CREATE", "TEMPLATE", template_id, {"codigo": payload["codigo"]})
        return TemplateService.get(connection, template_id)

    @staticmethod
    def add_variable(connection, actor, template_id: int, payload: dict, audit_change: bool = True) -> dict:
        require_role(actor, "ADMIN", "OAP")
        position = int(payload["posicion"])
        if position not in range(1, 8):
            raise DomainError("La posición de la variable debe estar entre 1 y 7")
        mode = payload.get("accumulation_mode", "SUM").upper()
        if mode not in {"SUM", "LATEST"}:
            raise DomainError("Modo de acumulación inválido")
        try:
            cursor = connection.execute(
                """INSERT INTO template_variables
                   (template_id, posicion, nombre, descripcion, accumulation_mode, requerida)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (template_id, position, payload["nombre"], payload.get("descripcion"), mode,
                 1 if payload.get("requerida") else 0),
            )
        except sqlite3.IntegrityError as exc:
            raise DomainError("La posición de la variable ya está configurada") from exc
        if audit_change:
            audit(connection, actor["id"], "CREATE", "TEMPLATE_VARIABLE", cursor.lastrowid,
                  {"template_id": template_id, "position": position})
        return as_dict(connection.execute("SELECT * FROM template_variables WHERE id = ?", (cursor.lastrowid,)).fetchone())

    @staticmethod
    def activate(connection, actor, template_id: int) -> dict:
        require_role(actor, "ADMIN", "OAP")
        variable_count = connection.execute(
            "SELECT COUNT(*) count FROM template_variables WHERE template_id = ?", (template_id,)
        ).fetchone()["count"]
        if not variable_count:
            raise DomainError("El template debe tener al menos una variable antes de activarse")
        connection.execute(
            "UPDATE templates SET estado = 'ACTIVO', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (template_id,),
        )
        audit(connection, actor["id"], "ACTIVATE", "TEMPLATE", template_id)
        return TemplateService.get(connection, template_id)

    @staticmethod
    def get(connection, template_id: int) -> dict:
        row = connection.execute(
            """SELECT t.*, l.codigo line_code, l.nombre line_name, d.codigo dependency_code,
                      d.nombre dependency_name
               FROM templates t
               JOIN lineas_estrategicas l ON l.id = t.linea_id
               JOIN dependencias d ON d.id = t.dependencia_id
               WHERE t.id = ?""", (template_id,)
        ).fetchone()
        if not row:
            raise DomainError("Template no encontrado", 404)
        result = dict(row)
        result["variables"] = [dict(variable) for variable in connection.execute(
            "SELECT * FROM template_variables WHERE template_id = ? ORDER BY posicion", (template_id,)
        ).fetchall()]
        return result

    @staticmethod
    def list(connection, year: int | None = None, status: str | None = None) -> list[dict]:
        conditions, params = [], []
        if year:
            conditions.append("t.vigencia = ?")
            params.append(year)
        if status:
            conditions.append("t.estado = ?")
            params.append(status.upper())
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = connection.execute(
            f"""SELECT t.id, t.codigo, t.vigencia, t.version, t.nombre, t.estado,
                       t.estado_indicador, t.unidad_medida,
                       l.nombre line_name, d.nombre dependency_name
                FROM templates t JOIN lineas_estrategicas l ON l.id = t.linea_id
                JOIN dependencias d ON d.id = t.dependencia_id
                {where} ORDER BY l.codigo, t.codigo""", params
        ).fetchall()
        return [dict(row) for row in rows]


class CaptureService:
    @staticmethod
    def assignments(connection, user, year: int, month: int) -> list[dict]:
        require_role(user, "ADMIN", "CARGADOR")
        dependency_filter = ""
        params: list[Any] = [year, year, month]
        if user["role"] == "CARGADOR":
            dependency_filter = "AND t.dependencia_id IN (SELECT dependencia_id FROM user_dependencias WHERE user_id = ?)"
            params.append(user["id"])
        rows = connection.execute(
            f"""SELECT t.id template_id, t.codigo, t.nombre, d.nombre dependency_name,
                       p.id period_id, p.estado period_status,
                       r.id report_id, COALESCE(r.estado, 'SIN_INICIAR') report_status
                FROM templates t JOIN dependencias d ON d.id = t.dependencia_id
                JOIN reporting_periods p ON p.vigencia = ? AND p.mes = ?
                LEFT JOIN formularios_respondidos r ON r.template_id = t.id AND r.period_id = p.id
                WHERE t.vigencia = ? AND t.estado = 'ACTIVO' {dependency_filter}
                ORDER BY d.nombre, t.codigo""",
            [year, month, year] + ([user["id"]] if user["role"] == "CARGADOR" else []),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def save_report(connection, user, template_id: int, year: int, month: int, payload: dict) -> dict:
        require_role(user, "ADMIN", "CARGADOR")
        template = connection.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
        if not template or template["estado"] != "ACTIVO":
            raise DomainError("El indicador no tiene un template activo", 404)
        if user["role"] == "CARGADOR":
            assignment = connection.execute(
                "SELECT 1 FROM user_dependencias WHERE user_id = ? AND dependencia_id = ?",
                (user["id"], template["dependencia_id"]),
            ).fetchone()
            if not assignment:
                raise DomainError("El indicador no pertenece a una dependencia asignada al usuario", 403)
        period = connection.execute(
            "SELECT * FROM reporting_periods WHERE vigencia = ? AND mes = ?", (year, month)
        ).fetchone()
        if not period or period["estado"] != "ABIERTO":
            raise DomainError("El periodo de reporte no está abierto")
        existing = connection.execute(
            "SELECT * FROM formularios_respondidos WHERE template_id = ? AND period_id = ?",
            (template_id, period["id"]),
        ).fetchone()
        if existing and existing["estado"] not in {"BORRADOR", "DEVUELTO"}:
            raise DomainError("El reporte ya fue enviado y no puede modificarse")

        values_by_position = {int(item["posicion"]): item.get("valor") for item in payload.get("variables", [])}
        definitions = connection.execute(
            "SELECT * FROM template_variables WHERE template_id = ? ORDER BY posicion", (template_id,)
        ).fetchall()
        if not definitions:
            raise DomainError("El template no tiene variables configuradas")
        missing = [row["posicion"] for row in definitions if row["requerida"] and values_by_position.get(row["posicion"]) is None]
        if missing:
            raise DomainError(f"Faltan variables requeridas: {missing}")

        if existing:
            report_id = existing["id"]
            connection.execute(
                """UPDATE formularios_respondidos SET reporter_id = ?, analisis_cualitativo = ?,
                       logros_dificultades = ?, observaciones_dependencia = ?, estado = 'BORRADOR',
                       updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (user["id"], payload.get("analisis_cualitativo"), payload.get("logros_dificultades"),
                 payload.get("observaciones_dependencia"), report_id),
            )
        else:
            cursor = connection.execute(
                """INSERT INTO formularios_respondidos
                   (template_id, period_id, reporter_id, analisis_cualitativo,
                    logros_dificultades, observaciones_dependencia)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (template_id, period["id"], user["id"], payload.get("analisis_cualitativo"),
                 payload.get("logros_dificultades"), payload.get("observaciones_dependencia")),
            )
            report_id = cursor.lastrowid

        formula_values: dict[str, float | None] = {}
        for definition in definitions:
            position = definition["posicion"]
            raw_value = values_by_position.get(position)
            value = float(raw_value) if raw_value not in (None, "") else None
            if definition["accumulation_mode"] == "SUM":
                previous = connection.execute(
                    """SELECT COALESCE(SUM(fv.valor_periodo), 0) total
                       FROM formulario_valores fv
                       JOIN formularios_respondidos r ON r.id = fv.report_id
                       JOIN reporting_periods p ON p.id = r.period_id
                       WHERE r.template_id = ? AND fv.variable_id = ? AND r.estado = 'APROBADO'
                         AND (p.vigencia < ? OR (p.vigencia = ? AND p.mes < ?))""",
                    (template_id, definition["id"], year, year, month),
                ).fetchone()["total"]
                accumulated = float(previous) + (value or 0) if value is not None or previous else None
            else:
                if value is not None:
                    accumulated = value
                else:
                    previous_row = connection.execute(
                        """SELECT fv.valor_periodo FROM formulario_valores fv
                           JOIN formularios_respondidos r ON r.id = fv.report_id
                           JOIN reporting_periods p ON p.id = r.period_id
                           WHERE r.template_id = ? AND fv.variable_id = ? AND r.estado = 'APROBADO'
                             AND (p.vigencia < ? OR (p.vigencia = ? AND p.mes < ?))
                           ORDER BY p.vigencia DESC, p.mes DESC LIMIT 1""",
                        (template_id, definition["id"], year, year, month),
                    ).fetchone()
                    accumulated = previous_row["valor_periodo"] if previous_row else None
            formula_values[f"V{position}"] = value
            connection.execute(
                """INSERT INTO formulario_valores (report_id, variable_id, valor_periodo, valor_acumulado)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(report_id, variable_id) DO UPDATE SET
                     valor_periodo = excluded.valor_periodo,
                     valor_acumulado = excluded.valor_acumulado""",
                (report_id, definition["id"], value, accumulated),
            )
        try:
            result = evaluate_formula(template["formula_expression"], formula_values)
        except FormulaError as exc:
            raise DomainError(str(exc)) from exc
        connection.execute(
            "UPDATE formularios_respondidos SET resultado_numerico = ? WHERE id = ?",
            (result, report_id),
        )
        audit(connection, user["id"], "SAVE_DRAFT", "REPORT", report_id,
              {"template_id": template_id, "year": year, "month": month})
        return CaptureService.get_report(connection, report_id)

    @staticmethod
    def submit(connection, user, report_id: int) -> dict:
        require_role(user, "ADMIN", "CARGADOR")
        report = connection.execute(
            """SELECT r.*, t.dependencia_id FROM formularios_respondidos r
               JOIN templates t ON t.id = r.template_id WHERE r.id = ?""", (report_id,)
        ).fetchone()
        if not report:
            raise DomainError("Reporte no encontrado", 404)
        if user["role"] == "CARGADOR" and not connection.execute(
            "SELECT 1 FROM user_dependencias WHERE user_id = ? AND dependencia_id = ?",
            (user["id"], report["dependencia_id"]),
        ).fetchone():
            raise DomainError("No tiene acceso a este reporte", 403)
        if report["estado"] not in {"BORRADOR", "DEVUELTO"}:
            raise DomainError("El reporte no está disponible para envío")
        connection.execute(
            "UPDATE formularios_respondidos SET estado = 'ENVIADO', submitted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (report_id,),
        )
        audit(connection, user["id"], "SUBMIT", "REPORT", report_id)
        return CaptureService.get_report(connection, report_id)

    @staticmethod
    def get_report(connection, report_id: int) -> dict:
        row = connection.execute(
            """SELECT r.*, t.codigo, t.nombre indicator_name, p.vigencia, p.mes,
                      d.nombre dependency_name
               FROM formularios_respondidos r JOIN templates t ON t.id = r.template_id
               JOIN reporting_periods p ON p.id = r.period_id
               JOIN dependencias d ON d.id = t.dependencia_id WHERE r.id = ?""",
            (report_id,),
        ).fetchone()
        if not row:
            raise DomainError("Reporte no encontrado", 404)
        result = dict(row)
        result["variables"] = [dict(value) for value in connection.execute(
            """SELECT tv.posicion, tv.nombre, tv.descripcion, tv.accumulation_mode,
                      fv.valor_periodo, fv.valor_acumulado
               FROM formulario_valores fv JOIN template_variables tv ON tv.id = fv.variable_id
               WHERE fv.report_id = ? ORDER BY tv.posicion""", (report_id,)
        ).fetchall()]
        result["revisiones_oap"] = [dict(review) for review in connection.execute(
            """SELECT o.*, u.full_name reviewer_name FROM oap_revisiones o
               JOIN users u ON u.id = o.reviewer_id WHERE o.report_id = ? ORDER BY o.created_at""",
            (report_id,),
        ).fetchall()]
        return result


class OapService:
    @staticmethod
    def queue(connection, user, status: str = "ENVIADO") -> list[dict]:
        require_role(user, "ADMIN", "OAP")
        rows = connection.execute(
            """SELECT r.id report_id, r.estado, r.resultado_numerico, r.submitted_at,
                      t.codigo, t.nombre indicator_name, d.nombre dependency_name,
                      p.vigencia, p.mes
               FROM formularios_respondidos r JOIN templates t ON t.id = r.template_id
               JOIN dependencias d ON d.id = t.dependencia_id
               JOIN reporting_periods p ON p.id = r.period_id
               WHERE r.estado = ? ORDER BY r.submitted_at""", (status.upper(),)
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def review(connection, user, report_id: int, payload: dict) -> dict:
        require_role(user, "ADMIN", "OAP")
        action = payload.get("decision", "COMENTARIO").upper()
        if action not in {"COMENTARIO", "APROBAR", "DEVOLVER"}:
            raise DomainError("Decisión de revisión inválida")
        report = connection.execute(
            "SELECT * FROM formularios_respondidos WHERE id = ?", (report_id,)
        ).fetchone()
        if not report or report["estado"] not in {"ENVIADO", "DEVUELTO"}:
            raise DomainError("El reporte no está disponible para revisión")
        application_status = payload.get("estado_aplicacion", "PENDIENTE").upper()
        if application_status not in {"PENDIENTE", "APLICADA", "NO_APLICADA"}:
            raise DomainError("Estado de aplicación inválido")
        connection.execute(
            """INSERT INTO oap_revisiones
               (report_id, reviewer_id, comentario, decision, estado_aplicacion)
               VALUES (?, ?, ?, ?, ?)""",
            (report_id, user["id"], payload.get("comentario"), action, application_status),
        )
        if action == "APROBAR":
            connection.execute(
                "UPDATE formularios_respondidos SET estado = 'APROBADO', approved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (report_id,),
            )
        elif action == "DEVOLVER":
            connection.execute(
                "UPDATE formularios_respondidos SET estado = 'DEVUELTO', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (report_id,),
            )
        audit(connection, user["id"], action, "REPORT", report_id,
              {"estado_aplicacion": application_status})
        return CaptureService.get_report(connection, report_id)


class PublicService:
    @staticmethod
    def indicators(connection, year: int, line_id: int | None = None,
                   dependency_id: int | None = None, active_only: bool = True) -> list[dict]:
        conditions = ["t.vigencia = ?"]
        params: list[Any] = [year]
        if line_id:
            conditions.append("t.linea_id = ?")
            params.append(line_id)
        if dependency_id:
            conditions.append("t.dependencia_id = ?")
            params.append(dependency_id)
        if active_only:
            conditions.append("t.estado = 'ACTIVO'")
        templates = connection.execute(
            f"""SELECT t.*, l.codigo line_code, l.nombre line_name,
                       d.codigo dependency_code, d.nombre dependency_name
                FROM templates t JOIN lineas_estrategicas l ON l.id = t.linea_id
                JOIN dependencias d ON d.id = t.dependencia_id
                WHERE {' AND '.join(conditions)} ORDER BY l.codigo, t.codigo""", params
        ).fetchall()
        result = []
        for template in templates:
            item = dict(template)
            item["variables"] = [dict(row) for row in connection.execute(
                "SELECT * FROM template_variables WHERE template_id = ? ORDER BY posicion", (template["id"],)
            ).fetchall()]
            reports = connection.execute(
                """SELECT r.id, r.resultado_numerico, r.analisis_cualitativo,
                          r.logros_dificultades, r.observaciones_dependencia, r.estado, p.mes
                   FROM formularios_respondidos r JOIN reporting_periods p ON p.id = r.period_id
                   WHERE r.template_id = ? AND p.vigencia = ? AND r.estado = 'APROBADO'
                   ORDER BY p.mes""", (template["id"], year)
            ).fetchall()
            item["resultados_mensuales"] = []
            for report in reports:
                report_data = dict(report)
                report_data["valores"] = [dict(row) for row in connection.execute(
                    """SELECT tv.posicion, fv.valor_periodo, fv.valor_acumulado
                       FROM formulario_valores fv JOIN template_variables tv ON tv.id = fv.variable_id
                       WHERE fv.report_id = ? ORDER BY tv.posicion""", (report["id"],)
                ).fetchall()]
                review = connection.execute(
                    """SELECT comentario, estado_aplicacion, created_at FROM oap_revisiones
                       WHERE report_id = ? ORDER BY created_at DESC LIMIT 1""", (report["id"],)
                ).fetchone()
                report_data["observacion_oap"] = as_dict(review)
                item["resultados_mensuales"].append(report_data)
            result.append(item)
        return result
