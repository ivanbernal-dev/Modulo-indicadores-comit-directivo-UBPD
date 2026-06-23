from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import load_settings
from app.database import Database
from app.security import hash_password


LINE_NAMES = {
    "1": "Línea 1. Investigación Humanitaria y Extrajudicial (Gestión de información e Investigación para la Búsqueda)",
    "2": "Línea 2. Gestión del conocimiento y preservación de memoria",
    "3": "Línea 3. Articulación interinstitucional e intersectorial para el fortalecimiento de las acciones de búsqueda humanitaria y extrajudicial",
    "4": "Línea 4. Sensibilización y comunicación para la búsqueda",
    "5": "Línea 5. Participación integral con enfoque diferencial: Plataforma de acción para la búsqueda",
    "6": "Línea 6. Soporte para la búsqueda",
}
MONTHS = {"Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5}


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", "_", normalized).strip("_")[:50]


def canonical_dependency(value: str) -> str:
    cleaned = " ".join((value or "Sin dependencia").split())
    return "Subdirección de Gestión Humana" if cleaned.upper() == "SGH" else cleaned


def formula_expression(value: str | None) -> str:
    text = (value or "").replace("×", "*")
    if re.search(r"V1t?\s*/\s*V2t?", text, re.I):
        return "(V1/V2)*100" if "100" in text or "%" in text else "V1/V2"
    if re.search(r"V1", text, re.I):
        return "V1"
    return "V1"


def accumulation_mode(definition: str | None) -> str:
    text = (definition or "").lower()
    if re.search(r"acumulad|total|meta|universo|porcentaje|denominador|programad|existente|proyectad", text):
        return "LATEST"
    return "SUM"


def number(value):
    return float(value) if isinstance(value, (int, float)) else None


def main():
    source_path = PROJECT_ROOT / "src" / "data" / "indicadores.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))["indicadores"]
    settings = load_settings()
    database = Database(settings.db_path)
    database.initialize()

    with database.transaction() as connection:
        admin = connection.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        if not admin:
            connection.execute(
                """INSERT INTO users (username, full_name, email, password_hash, role)
                   VALUES ('admin', 'Administrador UBPD', 'admin@demo.ubpd.local', ?, 'ADMIN')""",
                (hash_password("ChangeMe2026!"),),
            )
            admin = connection.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        cargador = connection.execute("SELECT * FROM users WHERE username = 'cargador.demo'").fetchone()
        if not cargador:
            connection.execute(
                """INSERT INTO users (username, full_name, email, password_hash, role)
                   VALUES ('cargador.demo', 'Usuario Cargador Demo', 'cargador@demo.ubpd.local', ?, 'CARGADOR')""",
                (hash_password("CargaDemo2026!"),),
            )
            cargador = connection.execute("SELECT * FROM users WHERE username = 'cargador.demo'").fetchone()

        line_ids = {}
        for key, name in LINE_NAMES.items():
            connection.execute(
                "INSERT OR IGNORE INTO lineas_estrategicas (codigo, nombre) VALUES (?, ?)", (f"L{key}", name)
            )
            line_ids[key] = connection.execute(
                "SELECT id FROM lineas_estrategicas WHERE codigo = ?", (f"L{key}",)
            ).fetchone()["id"]
        for month in range(1, 13):
            connection.execute(
                "INSERT OR IGNORE INTO reporting_periods (vigencia, mes, estado) VALUES (2026, ?, 'ABIERTO')",
                (month,),
            )

        imported = 0
        for item in source:
            line_match = re.match(r"Línea\s*([1-6])\.", item["linea"], re.I)
            if not line_match:
                continue
            dependency_name = canonical_dependency(item["dependencia"])
            dependency_code = "SGH" if dependency_name == "Subdirección de Gestión Humana" else slug(dependency_name)
            connection.execute(
                "INSERT OR IGNORE INTO dependencias (codigo, nombre) VALUES (?, ?)",
                (dependency_code, dependency_name),
            )
            dependency_id = connection.execute(
                "SELECT id FROM dependencias WHERE nombre = ?", (dependency_name,)
            ).fetchone()["id"]
            connection.execute(
                "INSERT OR IGNORE INTO user_dependencias (user_id, dependencia_id) VALUES (?, ?)",
                (cargador["id"], dependency_id),
            )
            existing = connection.execute(
                "SELECT id FROM templates WHERE codigo = ? AND vigencia = 2026 AND nombre = ?",
                (item["numeroIndicador"], item["nombreIndicador"]),
            ).fetchone()
            if existing:
                template_id = existing["id"]
            else:
                state = "INACTIVO" if item["estado2026"] == "Inactivo" else "ACTIVO"
                version = connection.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 next_version FROM templates WHERE codigo = ? AND vigencia = 2026",
                    (item["numeroIndicador"],),
                ).fetchone()["next_version"]
                cursor = connection.execute(
                    """INSERT INTO templates
                       (codigo, vigencia, version, linea_id, dependencia_id, nombre, objetivo,
                        definicion_operativa, formula_expression, formula_display, unidad_medida,
                        periodicidad, meta_anual, fuente_informacion, estado_indicador, estado, created_by)
                       VALUES (?, 2026, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["numeroIndicador"], version, line_ids[line_match.group(1)], dependency_id,
                     item["nombreIndicador"], item.get("objetivo"), item.get("definicionOperativa"),
                     formula_expression(item.get("formulaIndicador")), item.get("formulaIndicador"),
                     item.get("unidadMedida"), item.get("periodicidad") or "Mensual",
                     number(item.get("metaAnual2026")), item.get("fuenteInformacion"),
                     item["estado2026"], state, admin["id"]),
                )
                template_id = cursor.lastrowid
                for index, definition in enumerate(item.get("variables", []), 1):
                    if definition in (None, ""):
                        continue
                    connection.execute(
                        """INSERT INTO template_variables
                           (template_id, posicion, nombre, descripcion, accumulation_mode, requerida)
                           VALUES (?, ?, ?, ?, ?, 0)""",
                        (template_id, index, f"Variable {index}", str(definition), accumulation_mode(str(definition))),
                    )
                imported += 1

            variables = connection.execute(
                "SELECT * FROM template_variables WHERE template_id = ? ORDER BY posicion", (template_id,)
            ).fetchall()
            for month_name, month in MONTHS.items():
                monthly = item.get("resultadosMensuales", {}).get(month_name, {})
                if not monthly or not any([
                    monthly.get("formula") is not None,
                    monthly.get("analisisCualitativo"), monthly.get("logrosDificultades"),
                    monthly.get("observaciones"), monthly.get("observacionOAP"),
                ]):
                    continue
                period_id = connection.execute(
                    "SELECT id FROM reporting_periods WHERE vigencia = 2026 AND mes = ?", (month,)
                ).fetchone()["id"]
                report = connection.execute(
                    "SELECT id FROM formularios_respondidos WHERE template_id = ? AND period_id = ?",
                    (template_id, period_id),
                ).fetchone()
                if report:
                    report_id = report["id"]
                else:
                    cursor = connection.execute(
                        """INSERT INTO formularios_respondidos
                           (template_id, period_id, reporter_id, resultado_numerico, analisis_cualitativo,
                            logros_dificultades, observaciones_dependencia, estado, submitted_at, approved_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'APROBADO', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                        (template_id, period_id, admin["id"], number(monthly.get("formula")),
                         monthly.get("analisisCualitativo"), monthly.get("logrosDificultades"),
                         monthly.get("observaciones")),
                    )
                    report_id = cursor.lastrowid
                values = monthly.get("variables", [])
                for variable in variables:
                    value = number(values[variable["posicion"] - 1]) if variable["posicion"] <= len(values) else None
                    connection.execute(
                        """INSERT OR IGNORE INTO formulario_valores
                           (report_id, variable_id, valor_periodo, valor_acumulado) VALUES (?, ?, ?, ?)""",
                        (report_id, variable["id"], value, value),
                    )
                if monthly.get("observacionOAP"):
                    connection.execute(
                        """INSERT INTO oap_revisiones
                           (report_id, reviewer_id, comentario, decision, estado_aplicacion)
                           SELECT ?, ?, ?, 'COMENTARIO', 'PENDIENTE'
                           WHERE NOT EXISTS (SELECT 1 FROM oap_revisiones WHERE report_id = ? AND comentario = ?)""",
                        (report_id, admin["id"], monthly["observacionOAP"], report_id, monthly["observacionOAP"]),
                    )

    print(f"Importación completada. Templates nuevos: {imported}. Base: {settings.db_path}")


if __name__ == "__main__":
    main()
