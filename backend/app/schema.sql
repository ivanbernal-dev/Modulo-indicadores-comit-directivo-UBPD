PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lineas_estrategicas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1))
);

CREATE TABLE IF NOT EXISTS dependencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL UNIQUE,
    activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'CARGADOR', 'OAP', 'CONSULTA')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_dependencias (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dependencia_id INTEGER NOT NULL REFERENCES dependencias(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, dependencia_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL,
    vigencia INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    linea_id INTEGER NOT NULL REFERENCES lineas_estrategicas(id),
    dependencia_id INTEGER NOT NULL REFERENCES dependencias(id),
    nombre TEXT NOT NULL,
    objetivo TEXT,
    definicion_operativa TEXT,
    formula_expression TEXT NOT NULL,
    formula_display TEXT,
    unidad_medida TEXT,
    periodicidad TEXT NOT NULL DEFAULT 'Mensual',
    meta_anual REAL,
    fuente_informacion TEXT,
    estado_indicador TEXT NOT NULL DEFAULT 'Activo' CHECK (estado_indicador IN ('Activo', 'Modificado', 'Nuevo', 'Inactivo')),
    estado TEXT NOT NULL DEFAULT 'BORRADOR' CHECK (estado IN ('BORRADOR', 'ACTIVO', 'INACTIVO')),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (codigo, vigencia, version)
);

CREATE TABLE IF NOT EXISTS template_variables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    posicion INTEGER NOT NULL CHECK (posicion BETWEEN 1 AND 7),
    nombre TEXT NOT NULL,
    descripcion TEXT,
    accumulation_mode TEXT NOT NULL DEFAULT 'SUM' CHECK (accumulation_mode IN ('SUM', 'LATEST')),
    requerida INTEGER NOT NULL DEFAULT 0 CHECK (requerida IN (0, 1)),
    UNIQUE (template_id, posicion)
);

CREATE TABLE IF NOT EXISTS reporting_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vigencia INTEGER NOT NULL,
    mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    fecha_apertura TEXT,
    fecha_cierre TEXT,
    estado TEXT NOT NULL DEFAULT 'ABIERTO' CHECK (estado IN ('PROGRAMADO', 'ABIERTO', 'CERRADO')),
    UNIQUE (vigencia, mes)
);

CREATE TABLE IF NOT EXISTS formularios_respondidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES templates(id),
    period_id INTEGER NOT NULL REFERENCES reporting_periods(id),
    reporter_id INTEGER NOT NULL REFERENCES users(id),
    resultado_numerico REAL,
    analisis_cualitativo TEXT,
    logros_dificultades TEXT,
    observaciones_dependencia TEXT,
    estado TEXT NOT NULL DEFAULT 'BORRADOR' CHECK (estado IN ('BORRADOR', 'ENVIADO', 'DEVUELTO', 'APROBADO')),
    submitted_at TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (template_id, period_id)
);

CREATE TABLE IF NOT EXISTS formulario_valores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES formularios_respondidos(id) ON DELETE CASCADE,
    variable_id INTEGER NOT NULL REFERENCES template_variables(id),
    valor_periodo REAL,
    valor_acumulado REAL,
    UNIQUE (report_id, variable_id)
);

CREATE TABLE IF NOT EXISTS oap_revisiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES formularios_respondidos(id) ON DELETE CASCADE,
    reviewer_id INTEGER NOT NULL REFERENCES users(id),
    comentario TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('COMENTARIO', 'APROBAR', 'DEVOLVER')),
    estado_aplicacion TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado_aplicacion IN ('PENDIENTE', 'APLICADA', 'NO_APLICADA')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_name TEXT NOT NULL,
    vigencia INTEGER,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    result_json TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_templates_linea ON templates(linea_id, vigencia, estado);
CREATE INDEX IF NOT EXISTS idx_templates_dependencia ON templates(dependencia_id, vigencia, estado);
CREATE INDEX IF NOT EXISTS idx_reports_period ON formularios_respondidos(period_id, estado);
CREATE INDEX IF NOT EXISTS idx_reports_template ON formularios_respondidos(template_id, period_id);
CREATE INDEX IF NOT EXISTS idx_reviews_report ON oap_revisiones(report_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id, created_at);
