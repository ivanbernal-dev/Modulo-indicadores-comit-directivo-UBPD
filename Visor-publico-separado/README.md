# Módulo de indicadores del Comité Directivo — UBPD

Visor público e independiente para consultar los indicadores estratégicos del Comité Directivo por línea, dependencia, estado y periodo de reporte.

Este repositorio contiene el visor externo. La administración, captura mensual,
validación OAP y auditoría pertenecen a la zona autenticada de SISPLAN-Búsqueda.
El visor se alimenta mediante una API pública de solo lectura y nunca modifica datos.

## Funcionalidades

- Filtros por línea estratégica, dependencia y universo activo/inactivo.
- Tabla paginada con resultados mensuales de 2026.
- Visualización circular del avance de cada indicador.
- Panel de detalle con resultados, variables e información general.
- Consulta y actualización demostrativa del estado de observaciones OAP.
- Descarga del listado maestro utilizado como fuente.

## Desarrollo local

```bash
npm install
npm run dev
```

## Compilación

```bash
npm run build
```

Los datos de la demostración provienen de `LISTADO MAESTRO DE INDICADORES 2026 (4).xlsx`.

Para conectarlo al sistema, configure `VITE_PUBLIC_API_URL` con la URL del backend.
Si no existe esa variable, la aplicación conserva el JSON local como respaldo de demostración.

## Backend

La carpeta `backend/` contiene la API Python para templates anuales, captura mensual,
acumulados, revisión OAP, usuarios, auditoría e importación del maestro.

Consulte [`backend/README.md`](backend/README.md) para iniciar el servicio y revisar
las rutas disponibles.
