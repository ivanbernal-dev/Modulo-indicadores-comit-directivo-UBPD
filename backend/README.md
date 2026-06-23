# Backend — Indicadores Comité Directivo UBPD

Backend transaccional para administrar el ciclo anual de indicadores:

1. El administrador u OAP crea el template anual y sus variables.
2. El administrador asigna usuarios cargadores a una o más dependencias.
3. El cargador registra valores mensuales y contenido cualitativo.
4. El backend calcula la fórmula y los acumulados.
5. El cargador envía el reporte.
6. OAP comenta, devuelve o aprueba.
7. Solo los reportes aprobados alimentan el visor y los pipelines.

El prototipo usa Python 3.12 y SQLite sin dependencias externas. La capa de servicios concentra las reglas para facilitar una migración posterior a PostgreSQL y un framework institucional.

## Roles

| Rol | Responsabilidad |
|---|---|
| `ADMIN` | Usuarios, dependencias, periodos, templates, asignaciones y auditoría. |
| `CARGADOR` | Captura y envío mensual de indicadores de sus dependencias. |
| `OAP` | Administración metodológica, comentarios, devolución y aprobación. |
| `CONSULTA` | Acceso de solo lectura para seguimiento. |

## Inicio rápido

Desde la carpeta del proyecto:

```powershell
$python = "C:\ruta\a\python.exe"
& $python backend\scripts\init_db.py
& $python backend\scripts\import_master.py
Set-Location backend
& $python -m app.server
```

La API estará disponible en `http://127.0.0.1:8000`.

Credenciales exclusivamente para demostración:

- Administrador: `admin` / `ChangeMe2026!`
- Cargador: `cargador.demo` / `CargaDemo2026!`
- OAP: `oap.demo` / `OapDemo2026!`

Cambie estas contraseñas antes de publicar el backend.

## Pruebas

```powershell
python -m unittest discover -s backend\tests -v
```

## Principales rutas

| Método | Ruta | Rol |
|---|---|---|
| `POST` | `/api/auth/login` | Público |
| `GET` | `/api/auth/me` | Autenticado |
| `GET/POST` | `/api/admin/users` | ADMIN |
| `POST` | `/api/admin/periods` | ADMIN |
| `GET/POST` | `/api/templates` | Lectura / ADMIN-OAP |
| `POST` | `/api/templates/{id}/variables` | ADMIN-OAP |
| `POST` | `/api/templates/{id}/activate` | ADMIN-OAP |
| `GET` | `/api/capture/assignments?year=2026&month=6` | ADMIN-CARGADOR |
| `PUT` | `/api/capture/reports/{templateId}/{year}/{month}` | ADMIN-CARGADOR |
| `POST` | `/api/capture/reports/{reportId}/submit` | ADMIN-CARGADOR |
| `GET` | `/api/oap/reports?status=ENVIADO` | ADMIN-OAP |
| `POST` | `/api/oap/reports/{reportId}/review` | ADMIN-OAP |
| `GET` | `/api/public/indicators?year=2026` | Público |

## Ejemplo de captura mensual

```json
{
  "variables": [
    { "posicion": 1, "valor": 38 },
    { "posicion": 2, "valor": 23487 }
  ],
  "analisis_cualitativo": "El indicador avanza de acuerdo con lo programado.",
  "logros_dificultades": "Se consolidaron fuentes; persisten rezagos.",
  "observaciones_dependencia": "Se requiere ajuste metodológico."
}
```

La definición de las variables, fórmula, unidad, meta, objetivo y fuente no se repite mensualmente: pertenece al template de la vigencia.

Consulte [docs/architecture.md](docs/architecture.md) para el modelo relacional y las transiciones de estado.
