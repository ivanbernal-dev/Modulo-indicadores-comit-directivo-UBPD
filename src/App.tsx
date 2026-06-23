import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  Code2,
  Download,
  FileText,
  Flag,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
  Sprout,
  Users,
  X,
} from "lucide-react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import source from "./data/indicadores.json";

const MESES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
] as const;

type Mes = (typeof MESES)[number];
type Estado = "Activo" | "Modificado" | "Nuevo" | "Inactivo";
type Universo = "activos" | "inactivos";
type TabDetalle = "resultados" | "variables" | "informacion";
type EstadoOAP = "Pendiente" | "Aplicada" | "No aplicada";

const ALL_DEPENDENCIES = "__all_dependencies__";
const ALL_LINES = "__all_lines__";

type ResultadoMensual = {
  periodoFuente: string;
  variables: (string | number | null)[];
  formula: string | number | null;
  analisisCualitativo: string | null;
  logrosDificultades: string | null;
  observaciones: string | null;
  observacionOAP: string | null;
};

type Indicador = {
  id: string;
  consecutivo: string | number | null;
  linea: string;
  resultadoEstrategico: string | null;
  productoPAI: string | null;
  dependencia: string;
  responsablesAsociados: string | null;
  numeroIndicador: string;
  nombreIndicador: string;
  objetivo: string | null;
  definicionOperativa: string | null;
  formulaIndicador: string | null;
  variables: (string | number | null)[];
  periodicidad: string | null;
  unidadMedida: string | null;
  fuenteInformacion: string | null;
  lineaBase: string | number | null;
  metaAnual2026: string | number | null;
  estado2026: Estado;
  resultadosMensuales: Partial<Record<Mes, ResultadoMensual>>;
};

const CANONICAL_LINES: Record<string, string> = {
  "1": "Línea 1. Investigación Humanitaria y Extrajudicial (Gestión de información e Investigación para la Búsqueda)",
  "2": "Línea 2. Gestión del conocimiento y preservación de memoria",
  "3": "Línea 3. Articulación interinstitucional e intersectorial para el fortalecimiento de las acciones de búsqueda humanitaria y extrajudicial",
  "4": "Línea 4. Sensibilización y comunicación para la búsqueda",
  "5": "Línea 5. Participación integral con enfoque diferencial: Plataforma de acción para la búsqueda",
  "6": "Línea 6. Soporte para la búsqueda",
};

const canonicalLine = (value: string) => {
  const number = value.match(/^Línea\s*([1-6])\./i)?.[1];
  return number ? CANONICAL_LINES[number] : value.replace(/\s+/g, " ").trim();
};
const canonicalDependency = (value: string) => {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.toUpperCase() === "SGH" || normalized.toLowerCase() === "subdirección de gestión humana"
    ? "Subdirección de Gestión Humana"
    : normalized;
};

const fallbackIndicators = (source.indicadores as Indicador[]).map((item) => ({
  ...item,
  linea: canonicalLine(item.linea),
  dependencia: canonicalDependency(item.dependencia),
}));

const mapPublicApiIndicators = (rows: Record<string, any>[]): Indicador[] => rows.map((row) => {
  const variableDefinitions: (string | number | null)[] = Array(7).fill(null);
  for (const variable of row.variables ?? []) {
    if (variable.posicion >= 1 && variable.posicion <= 7) {
      variableDefinitions[variable.posicion - 1] = variable.descripcion || variable.nombre;
    }
  }
  const monthlyResults: Partial<Record<Mes, ResultadoMensual>> = {};
  for (const report of row.resultados_mensuales ?? []) {
    const month = MESES[Number(report.mes) - 1];
    if (!month) continue;
    const values: (string | number | null)[] = Array(7).fill(null);
    for (const value of report.valores ?? []) {
      if (value.posicion >= 1 && value.posicion <= 7) values[value.posicion - 1] = value.valor_periodo;
    }
    monthlyResults[month] = {
      periodoFuente: month,
      variables: values,
      formula: report.resultado_numerico,
      analisisCualitativo: report.analisis_cualitativo,
      logrosDificultades: report.logros_dificultades,
      observaciones: report.observaciones_dependencia,
      observacionOAP: report.observacion_oap?.comentario ?? null,
    };
  }
  return {
    id: String(row.id),
    consecutivo: row.id,
    linea: canonicalLine(row.line_name),
    resultadoEstrategico: null,
    productoPAI: null,
    dependencia: canonicalDependency(row.dependency_name),
    responsablesAsociados: null,
    numeroIndicador: row.codigo,
    nombreIndicador: row.nombre,
    objetivo: row.objetivo,
    definicionOperativa: row.definicion_operativa,
    formulaIndicador: row.formula_display || row.formula_expression,
    variables: variableDefinitions,
    periodicidad: row.periodicidad,
    unidadMedida: row.unidad_medida,
    fuenteInformacion: row.fuente_informacion,
    lineaBase: null,
    metaAnual2026: row.meta_anual,
    estado2026: row.estado_indicador as Estado,
    resultadosMensuales: monthlyResults,
  };
});

const cleanLabel = (value: string) => value.replace(/\s+/g, " ").trim();
const shortLine = (value: string) => cleanLabel(value).replace(/\s*\([^)]*\)\s*$/, "");
const numericValue = (value: string | number | null | undefined) => {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(String(value).replace("%", "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
};
const isPercentage = (item: Indicador) => {
  const text = `${item.unidadMedida ?? ""} ${item.formulaIndicador ?? ""}`.toLowerCase();
  return text.includes("porcentaje") || text.includes("%") || text.includes("*100") || text.includes("× 100");
};
const formatValue = (value: string | number | null | undefined, item: Indicador, dash = "-") => {
  if (value === null || value === undefined || value === "") return dash;
  if (typeof value === "string") return value;
  if (isPercentage(item)) {
    const percent = Math.abs(value) <= 1 ? value * 100 : value;
    return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(percent)}%`;
  }
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(value);
};
const latestProgress = (item: Indicador) => {
  const ordered = ["Mayo", "Abril", "Marzo", "Febrero"] as Mes[];
  const raw = ordered.map((month) => numericValue(item.resultadosMensuales[month]?.formula)).find((value) => value !== null);
  if (raw === null || raw === undefined) return 0;
  if (Math.abs(raw) <= 1) return Math.max(0, Math.min(100, raw * 100));
  if (isPercentage(item)) return Math.max(0, Math.min(100, raw));
  const meta = numericValue(item.metaAnual2026);
  return meta && meta > 0 ? Math.max(0, Math.min(100, (raw / meta) * 100)) : Math.min(100, raw);
};
const monthResult = (item: Indicador, month: Mes) => item.resultadosMensuales[month];
const compactText = (text: string | null, fallback = "Sin información reportada.") => text?.trim() || fallback;
const hasMonthlyValues = (result: ResultadoMensual | undefined) => Boolean(
  result && (result.formula !== null || result.variables.some((value) => value !== null)),
);
const formatVariableValue = (value: string | number | null) => {
  if (value === null || value === "") return "Sin reporte";
  if (typeof value === "number") return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(value);
  return value;
};
const usesLatestValueForAccumulation = (definition: string | number | null) => {
  const text = String(definition ?? "").toLowerCase();
  return /(acumulad|total|meta|universo|porcentaje|denominador|programad|existente|proyectad|línea base|linea base)/.test(text);
};
const accumulatedVariableValue = (item: Indicador, month: Mes, variableIndex: number) => {
  const monthIndex = MESES.indexOf(month);
  const values = MESES.slice(0, monthIndex + 1)
    .map((candidateMonth) => monthResult(item, candidateMonth)?.variables[variableIndex] ?? null);
  const numericValues = values
    .map((value) => numericValue(value))
    .filter((value): value is number => value !== null);
  if (numericValues.length) {
    return usesLatestValueForAccumulation(item.variables[variableIndex])
      ? numericValues[numericValues.length - 1]
      : numericValues.reduce((sum, value) => sum + value, 0);
  }
  return [...values].reverse().find((value) => value !== null) ?? null;
};

function ProgressRing({ value, color }: { value: number; color: string }) {
  const data = [{ value }, { value: Math.max(0, 100 - value) }];
  return (
    <div className="progress-ring" aria-label={`${Math.round(value)}% de avance`}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" innerRadius={19} outerRadius={25} startAngle={90} endAngle={-270} stroke="none">
            <Cell fill={color} /><Cell fill="#e7ebed" />
          </Pie>
          <Tooltip formatter={(v) => [`${Number(v).toFixed(0)}%`, "Avance"]} />
        </PieChart>
      </ResponsiveContainer>
      <strong>{Math.round(value)}%</strong>
    </div>
  );
}

function Sidebar() {
  const links = [
    [LayoutDashboard, "Dashboard"], [Users, "Usuarios"], [BarChart3, "Dependencias"],
    [FileText, "Templates"], [FolderOpen, "Registros"], [Code2, "Script Pipeline"],
    [CircleGauge, "Comité Directivo"], [BarChart3, "Indicadores"],
    [BarChart3, "Dashboard BI"], [ShieldCheck, "Auditoría"],
  ] as const;
  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark"><Sprout /></div>
        <strong>UBPD</strong>
        <span>Unidad de Búsqueda<br />de Personas dadas<br />por Desaparecidas</span>
      </div>
      <div className="admin-block"><small>ADMINISTRADOR</small><strong>Administrador UBPD</strong></div>
      <nav>
        {links.map(([Icon, label]) => (
          <button key={label} className={`side-link ${label === "Comité Directivo" ? "active" : ""}`}>
            <Icon size={17} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="logout"><LogOut size={17} />Cerrar Sesión</button>
    </aside>
  );
}

function DetailPanel({ item, onClose }: { item: Indicador; onClose: () => void }) {
  const [tab, setTab] = useState<TabDetalle>("resultados");
  const periods = (["Febrero", "Marzo", "Abril", "Mayo"] as Mes[])
    .map((month) => [month, monthResult(item, month)] as const)
    .filter(([, result]) => result && (result.formula !== null || result.analisisCualitativo || result.logrosDificultades || result.observaciones));
  return (
    <div className="drawer-overlay" onMouseDown={onClose}>
      <section className="detail-drawer" onMouseDown={(event) => event.stopPropagation()}>
        <button className="icon-close" onClick={onClose} aria-label="Cerrar detalle"><X size={18} /></button>
        <p className="drawer-kicker">Detalle del indicador</p>
        <h2>{item.numeroIndicador}. {item.nombreIndicador}</h2>
        <div className="detail-facts">
          <span><b>Fórmula:</b> {compactText(item.formulaIndicador)}</span>
          <span><b>Unidad:</b> {compactText(item.unidadMedida)}</span>
          <span><b>Meta 2026:</b> {formatValue(item.metaAnual2026, item)}</span>
        </div>
        <div className="tabs">
          <button className={tab === "resultados" ? "selected" : ""} onClick={() => setTab("resultados")}>Resultados mensuales</button>
          <button className={tab === "variables" ? "selected" : ""} onClick={() => setTab("variables")}>Variables (1–7)</button>
          <button className={tab === "informacion" ? "selected" : ""} onClick={() => setTab("informacion")}>Información general</button>
        </div>
        {tab === "resultados" && (
          <div className="detail-table-wrap">
            <table className="detail-table">
              <thead><tr><th>Periodo</th><th>Resultado</th><th>Análisis cualitativo</th><th>Logros y dificultades</th><th>Observaciones</th></tr></thead>
              <tbody>
                {periods.length ? periods.map(([month, result]) => (
                  <tr key={month}>
                    <td><b>{result?.periodoFuente || month}</b></td>
                    <td><b>{formatValue(result?.formula, item)}</b></td>
                    <td>{compactText(result?.analisisCualitativo ?? null)}</td>
                    <td>{compactText(result?.logrosDificultades ?? null)}</td>
                    <td>{compactText(result?.observaciones ?? null)}</td>
                  </tr>
                )) : <tr><td colSpan={5} className="empty-cell">Sin resultados reportados.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {tab === "variables" && (
          <div className="variables-grid">
            {item.variables.map((variable, index) => <article key={index}><small>Variable {index + 1}</small><p>{compactText(variable === null ? null : String(variable))}</p></article>)}
          </div>
        )}
        {tab === "informacion" && (
          <div className="info-grid">
            <article><small>Objetivo</small><p>{compactText(item.objetivo)}</p></article>
            <article><small>Definición operativa</small><p>{compactText(item.definicionOperativa)}</p></article>
            <article><small>Fuente de información</small><p>{compactText(item.fuenteInformacion)}</p></article>
          </div>
        )}
      </section>
    </div>
  );
}

function OapPanel({ item, month, onClose }: { item: Indicador; month: Mes; onClose: () => void }) {
  const [state, setState] = useState<EstadoOAP>("Pendiente");
  const [open, setOpen] = useState(false);
  const result = monthResult(item, month);
  const dates: Partial<Record<Mes, string>> = { Febrero: "28/02/2026", Marzo: "31/03/2026", Abril: "30/04/2026", Mayo: "31/05/2026" };
  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <section className="oap-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="icon-close" onClick={onClose} aria-label="Cerrar comentario"><X size={18} /></button>
        <p className="drawer-kicker">Comentario OAP — {month}</p>
        <h2>{item.numeroIndicador}. {item.nombreIndicador}</h2>
        <div className="oap-comment"><Flag size={18} /><div><b>Comentario de la OAP</b><p>{compactText(result?.observacionOAP ?? null)}</p></div></div>
        <div className="oap-meta">
          <article><small>Usuario que realizó el comentario</small><strong>Profesional OAP</strong><span>Oficina Asesora de Planeación</span></article>
          <article><small>Fecha del comentario</small><strong>{dates[month] ?? "2026"}</strong><span>Corte de seguimiento</span></article>
          <article className="state-card"><small>Estado de aplicación</small><button className="select-button" onClick={() => setOpen(!open)}>{state}<ChevronDown size={15} /></button>
            {open && <div className="state-menu">{(["Pendiente", "Aplicada", "No aplicada"] as EstadoOAP[]).map((value) => <button key={value} onClick={() => { setState(value); setOpen(false); }}><i className={value.toLowerCase().replace(" ", "-")} />{value}</button>)}</div>}
          </article>
        </div>
        <div className="modal-actions"><button className="ghost-button" onClick={onClose}>Cancelar</button><button className="save-button" onClick={onClose}>Guardar estado</button></div>
      </section>
    </div>
  );
}

function MonthlyVariablesPanel({ item, month, onClose }: { item: Indicador; month: Mes; onClose: () => void }) {
  const result = monthResult(item, month);
  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <section className="variables-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="icon-close" onClick={onClose} aria-label="Cerrar variables"><X size={18} /></button>
        <p className="drawer-kicker">Variables reportadas — {result?.periodoFuente || month}</p>
        <h2>{item.numeroIndicador}. {item.nombreIndicador}</h2>
        <div className="monthly-result-summary">
          <span>Resultado de la fórmula</span>
          <strong>{formatValue(result?.formula, item)}</strong>
          <small>{compactText(item.formulaIndicador, "Fórmula no definida")}</small>
        </div>
        <div className="monthly-variables-grid">
          {item.variables.map((definition, index) => {
            const value = result?.variables[index] ?? null;
            const accumulated = accumulatedVariableValue(item, month, index);
            return (
              <article key={index} className={value !== null ? "reported" : ""}>
                <div className="variable-heading"><small>Variable {index + 1}</small></div>
                <div className="variable-values">
                  <span><small>Valor del periodo</small><strong>{formatVariableValue(value)}</strong></span>
                  <span><small>Acumulado al mes</small><strong>{formatVariableValue(accumulated)}</strong></span>
                </div>
                <p>{compactText(definition === null ? null : String(definition), "Variable no definida")}</p>
              </article>
            );
          })}
        </div>
        {result?.analisisCualitativo && <div className="monthly-analysis"><small>Análisis del periodo</small><p>{result.analisisCualitativo}</p></div>}
        <div className="modal-actions"><button className="save-button" onClick={onClose}>Cerrar</button></div>
      </section>
    </div>
  );
}

export default function App() {
  const [indicatorData, setIndicatorData] = useState<Indicador[]>(fallbackIndicators);
  const [dataSource, setDataSource] = useState("Datos de demostración");
  const lines = useMemo(() => Object.values(CANONICAL_LINES).filter((value) => indicatorData.some((item) => item.linea === value)), [indicatorData]);
  const [line, setLine] = useState(ALL_LINES);
  const [universe, setUniverse] = useState<Universo>("activos");
  const lineItems = useMemo(() => indicatorData.filter((item) => line === ALL_LINES || item.linea === line), [indicatorData, line]);
  const dependencies = useMemo(() => [...new Set(lineItems
    .filter((item) => universe === "activos" ? item.estado2026 !== "Inactivo" : item.estado2026 === "Inactivo")
    .map((item) => item.dependencia))].sort(), [lineItems, universe]);
  const [dependency, setDependency] = useState(ALL_DEPENDENCIES);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [detailItem, setDetailItem] = useState<Indicador | null>(null);
  const [comment, setComment] = useState<{ item: Indicador; month: Mes } | null>(null);
  const [monthlyVariables, setMonthlyVariables] = useState<{ item: Indicador; month: Mes } | null>(null);

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_PUBLIC_API_URL?.replace(/\/$/, "");
    if (!apiUrl) return;
    fetch(`${apiUrl}/api/public/indicators?year=2026&active_only=false`)
      .then((response) => {
        if (!response.ok) throw new Error("No fue posible consultar SISPLAN-Búsqueda");
        return response.json();
      })
      .then((rows) => {
        setIndicatorData(mapPublicApiIndicators(rows));
        setDataSource("SISPLAN-Búsqueda · reportes aprobados");
      })
      .catch(() => setDataSource("Datos de demostración · API no disponible"));
  }, []);

  useEffect(() => {
    const nextDependencies = [...new Set(indicatorData
      .filter((item) => line === ALL_LINES || item.linea === line)
      .filter((item) => universe === "activos" ? item.estado2026 !== "Inactivo" : item.estado2026 === "Inactivo")
      .map((item) => item.dependencia))].sort();
    if (dependency !== ALL_DEPENDENCIES && !nextDependencies.includes(dependency)) {
      setDependency(ALL_DEPENDENCIES);
    }
  }, [indicatorData, line, universe, dependency]);

  const filtered = useMemo(() => indicatorData.filter((item) => {
    const stateMatch = universe === "activos" ? item.estado2026 !== "Inactivo" : item.estado2026 === "Inactivo";
    const queryMatch = !query || `${item.numeroIndicador} ${item.nombreIndicador}`.toLowerCase().includes(query.toLowerCase());
    const dependencyMatch = dependency === ALL_DEPENDENCIES || item.dependencia === dependency;
    const lineMatch = line === ALL_LINES || item.linea === line;
    return lineMatch && dependencyMatch && stateMatch && queryMatch;
  }), [indicatorData, line, dependency, universe, query]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  useEffect(() => setPage(1), [line, dependency, universe, query, pageSize]);
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize);
  const start = filtered.length ? (page - 1) * pageSize + 1 : 0;
  const end = Math.min(filtered.length, page * pageSize);

  return (
    <div className="public-app">
      <header className="public-site-header">
        <div className="public-header-inner">
          <div className="public-brand">
            <img src={`${import.meta.env.BASE_URL}logo-ubpd.png`} alt="Unidad de Búsqueda de Personas dadas por Desaparecidas - UBPD" />
          </div>
          <div className="public-system-name"><strong>Visor de Indicadores</strong><span>Comité Directivo</span></div>
        </div>
      </header>
      <main className="public-main">
        <section className="public-hero">
          <p>INFORMACIÓN INSTITUCIONAL</p>
          <h1>Indicadores del Comité Directivo</h1>
          <span>Consulta pública de resultados estratégicos por línea, dependencia y estado</span>
          <small>{dataSource}</small>
        </section>

        <section className="toolbar">
          <div className="filter-trail">
            <label><span>Línea estratégica:</span><select aria-label="Línea estratégica" title={line === ALL_LINES ? "Todas las líneas" : line} value={line} onChange={(event) => setLine(event.target.value)}><option value={ALL_LINES}>Todas las líneas</option>{lines.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label><span>Dependencia:</span><select aria-label="Dependencia" title={dependency === ALL_DEPENDENCIES ? "Todas las dependencias" : dependency} value={dependency} onChange={(event) => setDependency(event.target.value)}><option value={ALL_DEPENDENCIES}>Todas las dependencias</option>{dependencies.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="status-filter"><span>Estado del indicador:</span><select aria-label="Estado del indicador" value={universe} onChange={(event) => setUniverse(event.target.value as Universo)}><option value="activos">Activos</option><option value="inactivos">Inactivos</option></select></label>
          </div>
          <div className="toolbar-actions"><a className="excel-button" href={`${import.meta.env.BASE_URL}LISTADO-MAESTRO-INDICADORES-2026.xlsx`} download><Download size={16} />Exportar Excel</a></div>
        </section>

        <section className="table-card">
          <div className="table-heading"><div><h2>Tabla de indicadores</h2><span>{filtered.length} indicadores en esta selección</span></div><label className="search-box"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar indicador" /></label></div>
          <div className="table-scroll">
            <table className="indicators-table">
              <thead>
                <tr><th rowSpan={2}>N.º indicador</th><th rowSpan={2}>Nombre del indicador</th><th rowSpan={2}>Fórmula de indicador</th><th rowSpan={2}>Unidad de medida</th><th rowSpan={2}>Meta anual 2026</th><th rowSpan={2}>Estado 2026</th><th rowSpan={2}>Visual</th><th colSpan={12} className="monthly-title">Resultados mensuales 2026</th></tr>
                <tr>{MESES.map((month) => <th key={month}>{month.slice(0, 3)}</th>)}</tr>
              </thead>
              <tbody>
                {visible.map((item) => {
                  const progress = latestProgress(item);
                  const color = item.estado2026 === "Modificado" ? "#769aa0" : item.estado2026 === "Nuevo" ? "#8c7eac" : item.estado2026 === "Inactivo" ? "#a5adb5" : "#5f878d";
                  return <tr key={item.id}>
                    <td className="number-cell">{item.numeroIndicador}</td>
                    <td><button className="indicator-link" onClick={() => setDetailItem(item)}>{item.nombreIndicador}</button></td>
                    <td className="formula-cell">{compactText(item.formulaIndicador, "-")}</td>
                    <td>{compactText(item.unidadMedida, "-")}</td>
                    <td className="center-cell"><b>{formatValue(item.metaAnual2026, item)}</b></td>
                    <td className="center-cell"><span className={`status-badge ${item.estado2026.toLowerCase()}`}>{item.estado2026}</span></td>
                    <td className="center-cell"><ProgressRing value={progress} color={color} /></td>
                    {MESES.map((month) => {
                      const result = monthResult(item, month);
                      const hasComment = Boolean(result?.observacionOAP);
                      const hasValues = hasMonthlyValues(result);
                      return <td key={month} className="month-cell"><button disabled={!hasValues} className={hasValues ? "month-result has-values" : "month-result"} onClick={() => hasValues && setMonthlyVariables({ item, month })} title={hasValues ? "Ver variables del periodo" : "Sin resultado reportado"}>{formatValue(result?.formula, item)}</button><button disabled={!hasComment} className={hasComment ? "flag has-comment" : "flag"} onClick={() => hasComment && setComment({ item, month })} title={hasComment ? "Ver comentario OAP" : "Sin comentario OAP"}><Flag size={14} fill={hasComment ? "currentColor" : "none"} /></button></td>;
                    })}
                  </tr>;
                })}
                {!visible.length && <tr><td colSpan={19} className="empty-state">No hay indicadores para esta combinación de filtros.</td></tr>}
              </tbody>
            </table>
          </div>
          <footer className="table-footer">
            <div className="legend"><span><Flag size={14} fill="currentColor" className="red-flag" />Roja: existe comentario OAP</span><span><Flag size={14} />Blanca: sin comentario OAP</span></div>
            <div className="pagination"><span>Mostrando {start} a {end} de {filtered.length}</span><button disabled={page === 1} onClick={() => setPage(page - 1)}><ChevronLeft /></button>{Array.from({ length: Math.min(pageCount, 4) }, (_, index) => index + 1).map((value) => <button key={value} className={page === value ? "current" : ""} onClick={() => setPage(value)}>{value}</button>)}{pageCount > 4 && <><span>…</span><button className={page === pageCount ? "current" : ""} onClick={() => setPage(pageCount)}>{pageCount}</button></>}<button disabled={page === pageCount} onClick={() => setPage(page + 1)}><ChevronRight /></button><select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}><option value={5}>5 por página</option><option value={10}>10 por página</option><option value={20}>20 por página</option></select></div>
          </footer>
        </section>
        <footer className="source-note">Fuente administrada en SISPLAN-Búsqueda · {indicatorData.length} indicadores disponibles · Solo se publican reportes aprobados</footer>
      </main>
      {detailItem && <DetailPanel item={detailItem} onClose={() => setDetailItem(null)} />}
      {comment && <OapPanel item={comment.item} month={comment.month} onClose={() => setComment(null)} />}
      {monthlyVariables && <MonthlyVariablesPanel item={monthlyVariables.item} month={monthlyVariables.month} onClose={() => setMonthlyVariables(null)} />}
    </div>
  );
}
