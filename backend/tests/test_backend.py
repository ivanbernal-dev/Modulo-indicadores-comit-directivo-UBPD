from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import Database
from app.formulas import FormulaError, evaluate_formula
from app.services import CaptureService, OapService, TemplateService, UserService


class BackendWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "test.db")
        self.database.initialize()
        with self.database.transaction() as connection:
            UserService.create(connection, None, {
                "username": "admin", "full_name": "Admin", "password": "AdminTest2026!", "role": "ADMIN"
            })
            self.admin = connection.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
            self.loader = UserService.create(connection, self.admin, {
                "username": "loader", "full_name": "Loader", "password": "LoaderTest2026!", "role": "CARGADOR"
            })
            self.oap = UserService.create(connection, self.admin, {
                "username": "oap", "full_name": "OAP", "password": "OapTest2026!", "role": "OAP"
            })
            line_id = connection.execute(
                "INSERT INTO lineas_estrategicas (codigo, nombre) VALUES ('L1', 'Línea 1')"
            ).lastrowid
            dependency_id = connection.execute(
                "INSERT INTO dependencias (codigo, nombre) VALUES ('DEP', 'Dependencia')"
            ).lastrowid
            connection.execute(
                "INSERT INTO user_dependencias (user_id, dependencia_id) VALUES (?, ?)",
                (self.loader["id"], dependency_id),
            )
            connection.executemany(
                "INSERT INTO reporting_periods (vigencia, mes, estado) VALUES (2026, ?, 'ABIERTO')",
                [(1,), (2,)],
            )
            template = TemplateService.create(connection, self.admin, {
                "codigo": "L1-TEST-001", "vigencia": 2026, "linea_id": line_id,
                "dependencia_id": dependency_id, "nombre": "Indicador de prueba",
                "formula_expression": "(V1/V2)*100",
                "variables": [
                    {"posicion": 1, "nombre": "Logros del mes", "accumulation_mode": "SUM", "requerida": True},
                    {"posicion": 2, "nombre": "Meta total", "accumulation_mode": "LATEST", "requerida": True},
                ],
            })
            TemplateService.activate(connection, self.admin, template["id"])
            self.template_id = template["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_capture_accumulation_and_oap_approval(self):
        with self.database.transaction() as connection:
            loader = connection.execute("SELECT * FROM users WHERE username = 'loader'").fetchone()
            oap = connection.execute("SELECT * FROM users WHERE username = 'oap'").fetchone()
            january = CaptureService.save_report(connection, loader, self.template_id, 2026, 1, {
                "variables": [{"posicion": 1, "valor": 2}, {"posicion": 2, "valor": 10}],
                "analisis_cualitativo": "Inicio del indicador",
            })
            self.assertEqual(january["resultado_numerico"], 20)
            CaptureService.submit(connection, loader, january["id"])
            OapService.review(connection, oap, january["id"], {"decision": "APROBAR"})
            february = CaptureService.save_report(connection, loader, self.template_id, 2026, 2, {
                "variables": [{"posicion": 1, "valor": 3}, {"posicion": 2, "valor": 10}],
                "analisis_cualitativo": "Segundo periodo",
            })
            self.assertEqual(february["resultado_numerico"], 30)
            values = {item["posicion"]: item for item in february["variables"]}
            self.assertEqual(values[1]["valor_acumulado"], 5)
            self.assertEqual(values[2]["valor_acumulado"], 10)

    def test_formula_rejects_code_execution(self):
        with self.assertRaises(FormulaError):
            evaluate_formula("__import__('os').system('dir')", {"V1": 1})


if __name__ == "__main__":
    unittest.main()
