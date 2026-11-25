# Diagnosis: El gate `embed-check` aplana fallos de carga a `E_MODEL_INVALID` y F6 los silencia

**Issue:** local (reporte del dueño, 2026-11-25) — sin issue remoto
**Date:** 2026-11-25
**Severity:** high
**Status:** diagnosed

---

## Summary

Dos fallos de error del wizard (A: instalación, B: swap) comparten una sola raíz: el gate
`embed-check` del flow aplana **cualquier** excepción de carga/descarga a
`{"ok":false,"error_code":"E_MODEL_INVALID","detail":…}`
(`obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/__main__.py:111-136`, docstring `:116-120`),
y el lado Rust `parse_gate` lee solo `ok/model/dims/rss`, descarta `detail` y `error_code`
(`crates/tepochcalli/src/application/flow_contract.rs:82-88`) y mapea `Some(false)` a
`WizardError::ModelInvalid` (`:93-98`), cuyo `Display` es `not an embedding model`
(`crates/tepochcalli/src/domain/error.rs:39-41`). Ese código está reservado por
`specs/spec-embeddings.md:153` y `docs/adr/adr-008-transparencia-hardware-cambio-modelo.md:50`
al **pre-filtro de tags de la ruta 3** (ID libre de HuggingFace), no a los presets. En B, el
`device` elegido por presencia de `nvidia-smi`/`rocm-smi` se escribe en la config **antes** del
gate y el gate lo hereda, de modo que un fallo de carga CUDA se informa como «modelo inválido».
En A, el mismo gate falla en F6 y la rama degradada no invoca `report_failure`, así que no hay
panel ni log. Relacionado con [fix03](fix03-desinstall-lento-por-venv.md) — mismo release beta.3.

## Symptoms

| | A — instalación (F6) | B — swap de embedder |
| --- | --- | --- |
| Lo que ve el usuario | Vuelve el prompt sin panel de error; tras ~2 m 29 s de pausa aparente | Panel «install failed / not an embedding model» |
| Lo que escriben los logs | Nada: `cli/report.rs:69-81` es el único que escribe panel/log y aquí no se llama | Panel con el `Display` de `ModelInvalid` (`cli/commands.rs:164-165`) |
| Estado posterior | `model: (sin configurar)`, `dims: (sin dato)`, `db/: 0` (`swap.rs:127-134`, `phase7.rs:55-65`) | `abort_swap` devuelve los bytes previos (`application/swap.rs:169-174`) |

- La hipótesis «falta `--confirm`» está **descartada**: `crates/tepochcalli/src/cli/home.rs:160,192-198`
  empuja `--confirm`.
- Los ~2 m 29 s no son un crash: son el `wait_key` de H11
  (`crates/tepochcalli/src/adapters/ui_ratatui.rs:349-359`); el proceso termina con exit 0
  (`crates/tepochcalli/src/application/install_phases.rs:375`).
- En A, `cli/install.rs:437-452` solo reporta `UserAborted`/`Internal`/`OfflineNoCache`; para el
  resto, `:453-460` compensa a `none_config`, marca F6 *done*, escribe un `writeln!` a stderr y
  devuelve `Ok(configure_later)` **sin** `report_failure`. `none_config` escribe solo
  `provider = "none"` (`crates/tepochcalli/src/application/embedder_config.rs:63-69`), de ahí el
  estado «sin configurar / sin dato / 0».
- En B: `application/swap.rs:327-330`, brazo `PresetDefault` → `pending_local` **sin** pre-filtro
  HF; `choose_device` (`:343-358`) ofrece `cuda` solo por presencia de
  `nvidia-smi`/`rocm-smi` (`adapters/host.rs:114-131`, `embedder_options.rs:65-92`);
  `swap.rs:156-168` escribe la config con `device=cuda` ANTES del gate; el gate no recibe
  `--device` (`flow_contract.rs:47-61`) y hereda el device de la config ⇒ la carga CUDA falla ⇒
  `E_MODEL_INVALID` falso ⇒ `abort_swap` (`:169-174`).

## Root Cause

La raíz compartida es la **pérdida de la causa del error en la frontera del gate**: el flow
convierte todo fallo de carga/descarga en un código que significa otra cosa y el wizard descarta
el único campo (`detail`) que podría distinguirlos.

> ¿Por qué un fallo de CUDA se llama «not an embedding model»? → `cmd_embed_check`
> (`__main__.py:111-136`) captura `Exception` sin discriminar y devuelve `ERROR_MODEL_INVALID`
> con el `detail` truncado; `parse_gate` (`flow_contract.rs:82-98`) ignora `detail`/`error_code` y
> `gate_verdict` mapea todo `ok:false` a `ModelInvalid`, reservado en realidad al pre-filtro de
> tags de la ruta 3 (`specs/spec-embeddings.md:153`, ADR-008:50). El `detail` real muere en el
> parseo.
>
> ¿Por qué aparece CUDA si el usuario eligió un preset? → `swap.rs:327-330` no aplica el
> pre-filtro HF al preset, `choose_device` (`:343-358`) infiere `cuda` de la presencia de
> `nvidia-smi`/`rocm-smi`, y `swap.rs:156-168` escribe `device=cuda` en la config antes del gate.
> Como `spawn_gate` no pasa `--device` (`flow_contract.rs:55-60`) y `build_embedder_for_model`
> lee la config viva (`__main__.py:74-85`), el gate hereda exactamente el device que lo hace
> fallar.
>
> ¿Por qué el fallo A no deja rastro? → `run_f6_or_degraded` (`cli/install.rs:437-460`) trata
> `ModelInvalid` como error degradable: compensa a `none_config`, marca la fase *done* y devuelve
> `Ok(configure_later)`; el único productor de panel/log es `report_failure` (`cli/report.rs:69-81`),
> que no se invoca en esa rama. El silence es una consecuencia del mapeo erróneo, no un bug
> independiente.

## Impact

| Dimension | Assessment |
| --- | --- |
| Users affected | subset (quienes usan presets en hosts con `nvidia-smi`/`rocm-smi`, y quienes fallan F6 por carga) |
| Functionality | broken en swap (aborta); degraded en install (deja el RAG sin embedder y sin aviso) |
| Data integrity | safe (swap revierte el snapshot; install compensa a `provider = "none"` sin índice) |
| Reproducibility | always en el entorno con device CUDA inferido; environment-specific para el resto |

La degradación sin aviso es el daño principal: el usuario cree que la instalación terminó bien y
descubre después `db/: 0`. El panel de B, aunque engañoso, al menos expone el fallo.

## Environment

- **Platform:** wizard Rust TUI (`ratatui` 0.30 + `crossterm` 0.29) sobre mount fuseblk/NTFS-3G.
- **Version:** rama `fix/wizard`, release beta.3 (2026-11-25).
- **Configuration:** ruta preset en swap con `PresetDefault` → `pending_local`
  (`application/swap.rs:327-330`); `embedding.device=cuda` escrito en config antes del gate
  (`swap.rs:156-168`); gate sin `--device` (`flow_contract.rs:55-60`).

## Proposed Solution

Cuatro pasos, sin tocar H5 ni `process::exit`, y manteniendo la política degradada de exit 0:

1. **Separar las causas en el flow.** En
   `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/__main__.py:111-136`, distinguir
   «tags no-embedding» (que sigue siendo `E_MODEL_INVALID`) de «fallo de carga/descarga» (nuevo
   código de error), conservando el `detail` real en lugar del texto fijo; actualizar el docstring
   `:116-120` y el `shortcut` que hoy lo justifica.
2. **Propagar el error en el wizard.** En `crates/tepochcalli/src/application/flow_contract.rs:82-98`,
   conservar y propagar `detail` (y `error_code`), y mapear `ok:false` a `ModelInvalid` **solo**
   para la ruta 3 (ID libre de HF) y a `PhaseFailed` para presets, de acuerdo con
   `specs/spec-embeddings.md:153` y ADR-008:50.
3. **Romper la contaminación device→gate.** Pasar `--device` explícito al `embed-check`:
   añadirlo en `spawn_gate` (`flow_contract.rs:47-61`) y aceptarlo en el CLI
   (`__main__.py:147-153`), para que el gate no herede el `embedding.device` de la config viva
   (`__main__.py:74-85`) escrita en `swap.rs:156-168`.
4. **Hacer visible el fallo A.** En `cli/install.rs::run_f6_or_degraded`, invocar `report_failure`
   para todo error salvo `UserAborted`, manteniendo la política degradada exit-0 y el checklist
   antes de `wait_key` (`cli/report.rs:69-81`, `adapters/ui_ratatui.rs:349-359`).

**Cobertura que hoy no detecta el fallo** (a añadir con el fix):

| Test | Hueco |
| --- | --- |
| `int_swap_commit.rs::swap_preserves_a_hand_written_device:274-319` | el gate fake siempre devuelve ok |
| `int_swap_run.rs::swap_rejected_gate_rolls_back_to_zero_state:242-262` | pinea `ok:false` → `ModelInvalid` como correcto |
| `embedder_gate.rs::gate_false_is_model_invalid_and_garbage_is_phase_failed:261-271` | pinea el mapeo erróneo como correcto |
| `e2e_install_atomicity.rs::f6_failure_compensates_to_degraded_path5:266-299` | llama `compensate_phase6` directamente, no afirma panel/log |
| `e2e_failure_panel.rs:51-73` | cubre `UserAborted`, que sí se reporta |

**ADR: no necesario.** No hay cambio de contrato ni de decisión D1-D8: es una corrección de hechos
que contradicen `specs/spec-embeddings.md:153` y ADR-008:50; no se re-editan ADRs Accepted. Registrar
en `docs/BACKLOG.md` §8.

## Workarounds

> ⚠️ **WORKAROUND** (hasta aplicar el fix)
>
> - En B: usar la re-entrada del wizard para elegir `device=cpu` explícitamente (la elección de
>   device es explícita y re-entrable, ADR-015) en lugar del `cuda` inferido por
>   `embedder_options.rs:65-92`.
> - En A: repetir la configuración por la ruta `HuggingFaceId`, que es la única que captura
>   `ModelInvalid` con reintento (`embedder_menu.rs:137-144`); la ruta preset (`:134-145`) no
>   reintenta. Revisar después que `db/` vuelve a tener entradas (`swap.rs:127-134`).

## Recurrences

| Date | Similar Issue | Variation |
| --- | --- | --- |
| 2026-11-25 | B: swap con preset y `device=cuda` | Panel «install failed / not an embedding model»; `--confirm` presente |
| 2026-11-25 | A: F6 de instalación con el mismo gate | Sin panel ni log; degradado a `provider = "none"` y exit 0 |

**Ambas variantes del mismo release beta.3; ver [fix03](fix03-desinstall-lento-por-venv.md) para el
tercer síntoma del release (H8 lento), de raíz distinta.**

## References

- Flow gate y lectura de config viva: `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/__main__.py:74-85,111-136,147-153`
- Parseo y spawn del gate: `crates/tepochcalli/src/application/flow_contract.rs:47-61,82-98`
- `Display` de `ModelInvalid`: `crates/tepochcalli/src/domain/error.rs:39-41`
- Swap (device, config antes del gate, abort): `crates/tepochcalli/src/application/swap.rs:127-134,156-174,327-330,343-358`
- Inferencia de CUDA: `crates/tepochcalli/src/adapters/host.rs:114-131`, `crates/tepochcalli/src/application/embedder_options.rs:65-92`
- Menú F6 y rama degradada: `crates/tepochcalli/src/cli/embedder_menu.rs:134-145,161-169`, `crates/tepochcalli/src/cli/install.rs:437-460`
- Panel/log y pausa: `crates/tepochcalli/src/cli/report.rs:69-81`, `crates/tepochcalli/src/cli/commands.rs:164-165`, `crates/tepochcalli/src/adapters/ui_ratatui.rs:349-359`
- Reserva del código: [specs/spec-embeddings.md:153](../../specs/spec-embeddings.md), [docs/adr/adr-008-transparencia-hardware-cambio-modelo.md:50](../adr/adr-008-transparencia-hardware-cambio-modelo.md)
- Diagnóstico hermano (mismo release beta.3): [fix03-desinstall-lento-por-venv.md](fix03-desinstall-lento-por-venv.md)

---

**Diagnosis created by `/diagnosis`. Update this file if the fix reveals additional insights.**
