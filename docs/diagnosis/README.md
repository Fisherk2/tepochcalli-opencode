# Diagnósticos técnicos

Este directorio contiene **solo diagnósticos de issues** del proyecto: análisis de causa raíz
de bugs, incidentes y problemas técnicos, con un formato común para que sean trazables.

La **evidencia de aceptación** (mediciones E2E de los 7 criterios de [UH.md](../UH.md)) **no vive
aquí**: se publica en [`docs/acceptance/`](../acceptance/README.md).

## Propósito

- Capturar el análisis de causa raíz de bugs, incidentes y problemas técnicos
- Dejar un registro buscable de diagnósticos pasados para consulta futura
- Detectar patrones recurrentes que merezcan automatización o una corrección sistémica

## Índice

| Fichero | Issue | Fecha | Severidad |
| --- | --- | --- | --- |
| [fix01-conversor-satura-contexto-llm.md](fix01-conversor-satura-contexto-llm.md) | El conversor satura el contexto del LLM | 2026-10-30 | — |

<!-- Añadir aquí las entradas según se creen diagnósticos. La evidencia de aceptación
     (Phase 6: criterios 1-7) no vive aquí: se publica en `docs/acceptance/`. -->

## Flujo de trabajo

1. Se identifica un issue (reporte de usuario, alerta automatizada, revisión de código)
2. Se ejecuta `/diagnosis` para analizar y documentar la causa raíz
3. Se ejecuta `/plan` para crear el plan de ejecución de la corrección
4. Se actualiza el diagnóstico si la corrección revela información adicional

## Plantilla

Usa `diagnosis-template.md` como punto de partida para nuevos diagnósticos.

## Convención de nombres

<!-- markdownlint-disable MD040 -->
```
fix<NNN>-<short-description>.md
```
<!-- markdownlint-enable MD040 -->

Donde `<NNN>` es un número secuencial (01, 02, ...) y `<short-description>` es un resumen
kebab-case del issue.
