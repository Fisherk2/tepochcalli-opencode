# Diagnosis: El desinstall (H8) tarda ~4 m 21 s por el borrado secuencial del venv

**Issue:** local (reporte del dueño, 2026-11-25) — sin issue remoto
**Date:** 2026-11-25
**Severity:** medium
**Status:** diagnosed

---

## Summary

La fase H8 (`desinstall`) elimina los tres scopes con `std::fs::remove_dir_all`
(`crates/tepochcalli/src/application/maintenance.rs:244`) sobre `.opencode/` y `.tepochcalli/`.
En este montaje fuseblk/NTFS-3G, `.tepochcalli/venv` mide **2,1 G y 51.386 entradas**
(45.274 ficheros + 6.108 directorios) y todo `.tepochcalli/` **101.413 entradas con dos venvs**;
`.opencode/` solo 11 M y 891 entradas. El borrado secuencial implica del orden de 150–300 k
mutaciones de metadatos amplificadas por el filesystem ⇒ **~4 m 21 s observados**, con apariencia
de cuelgo. El backup **no** es el culpable: cubre solo tres scopes irreemplazables
(`maintenance.rs:52-57`) y copia fichero a fichero sin seguir symlinks (`:331-368`), del orden de
3–5 k syscalls ≈ segundos. Relacionado con [fix02](fix02-wizard-gate-modelinvalid-y-f6-silencioso.md)
— mismo release beta.3, raíz distinta.

## Symptoms

- H8 tarda ~4 m 21 s entre la confirmación y el panel «Desinstall completo»
  (`maintenance.rs:262-268`); no hay crash ni error, solo espera.
- El directorio que domina el tiempo es `.tepochcalli/venv`: 2,1 G, 51.386 entradas
  (45.274 ficheros + 6.108 dirs); `.tepochcalli/` completo: 101.413 entradas con dos venvs.
- `.opencode/` es trivial comparado: 11 M, 891 entradas.
- La pausa «Pulsa cualquier tecla» (`crates/tepochcalli/src/adapters/ui_ratatui.rs:349-359`) es
  espera humana, **cero FS**: no explica la lentitud.
- El backup se crea primero (`maintenance.rs:220-225`) y su ámbito es solo `.opencode/`,
  `opencode.json`, `.tepochcalli/config/` y `.tepochcalli/pyproject.toml` (`:52-57`); copiar
  esos ficheros no es el cuello de botella.

## Root Cause

La causa es una primitiva de borrado secuencial sobre un árbol con decenas de miles de entradas
en un filesystem donde cada mutación de metadatos es cara.

> ¿Por qué tarda minutos si el backup es pequeño? → `remove_dir_all` en `maintenance.rs:244`
> recorre y desvincula entradas una a una; con 101.413 entradas en `.tepochcalli/` (dos venvs)
> resultan ~150–300 k mutaciones secuenciales amplificadas por fuseblk/NTFS-3G, frente a los
> 3–5 k syscalls del backup `copy_tree` (`:331-368`, sin seguir symlinks).
>
> ¿Por qué no basta con no hacer backup del venv? → ya es así: `UNINSTALL_BACKUP_SCOPES`
> (`maintenance.rs:52-57`) excluye `venv/`, `db/`, `models/` y `bin/` por ser regenerables y
> porque copiarlos puede agotar el disco (comentario `:48-51`). El coste está enteramente en el
> **borrado**, no en la copia. Reducir el backup sería además inseguro: `config/` puede contener
> API key y su `.gitignore` `"*"` con permisos 0700/0600 (`:301-303`) es intocable.
>
> ¿Por qué parece colgado? → porque el único trabajo visible es el panel de inicio y el de
> final (`:262-268`); entre ambos no hay progreso por entrada, y la pausa de H11
> (`ui_ratatui.rs:349-359`) es solo interacción humana posterior, no actividad de disco.

## Impact

| Dimension | Assessment |
| --- | --- |
| Users affected | all (quienes ejecutan `desinstall` sobre este montaje) |
| Functionality | degraded (termina correctamente, pero con espera de minutos) |
| Data integrity | safe (backup antes de borrar, 3 scopes exactos, rollback por backup con nombre) |
| Reproducibility | environment-specific (fuseblk/NTFS-3G; en un filesystem nativo el coste es mucho menor) |

No hay pérdida de notas ni de `.obsidian/`: los scopes son fijos
(`UNINSTALL_SCOPES`, `maintenance.rs:47`) y el backup se crea antes de tocar nada (`:220-225`).
El riesgo real es operativo: el usuario interrumpe un borrado a medias por creer que se colgó.

## Environment

- **Platform:** mount fuseblk/NTFS-3G (mismo límite de filesystem documentado para `cargo` en
  AGENTS.md); medición del dueño 2026-11-25.
- **Version:** rama `fix/wizard`, release beta.3 (2026-11-25).
- **Configuration:** `.tepochcalli/venv` 2,1 G / 51.386 entradas; `.tepochcalli/` 101.413
  entradas (dos venvs); `.opencode/` 11 M / 891 entradas; backup con 4 scopes
  (`maintenance.rs:52-57`).

## Proposed Solution

1. **Sustituir la primitiva de borrado.** Reemplazar `std::fs::remove_dir_all` en
   `crates/tepochcalli/src/application/maintenance.rs:244` por un helper de borrado
   *fd-relative* con paralelismo acotado (N=8 vía `std::thread::scope`), **sin dependencias
   nuevas**.
2. **Recorrido seguro.** Usar `DirEntry::file_type()` (que no sigue symlinks), borrar los ficheros
   y hacer `remove_dir` *bottom-up*; mantener la distinción scope→tipo de `maintenance.rs:238-245`
   para que un `.tepochcalli` corrupto como fichero falle tipado y no borre otra cosa.
3. **Reutilizar la taxonomía existente.** Aplicar `map_fs` (`maintenance.rs:277-283`) para ENOSPC
   → `DiskFull` y el resto → `PermissionDenied`, y conservar la tolerancia `NotFound`
   (`:248`) para entradas que desaparecen durante el recorrido.
4. **Código nativo de Windows intacto.** Bajo `#[cfg(windows)]` conservar
   `std::fs::remove_dir_all`: el cambio se dirige al comportamiento del montaje fuseblk/NTFS-3G,
   no a la semántica de Windows.
5. **No tocar la seguridad ni el contrato.** Preservar el backup antes de borrar
   (`:220-225`), los 3 scopes exactos (`:47`), la cancelación por entrada (`:227`), los paneles y
   el rollback por backup con nombre (`:231-234`), y la privacidad 0700/0600 + `.gitignore` `"*"`
   del backup (`:301-303`). El `.gitignore` con `"*\n"` es intocable: `config/` puede tener una
   API key.
6. **Medir A/B antes de aceptar.** Añadir contadores deterministas `entries_removed` y
   `workers_used` y comparar el tiempo del helper contra `remove_dir_all` sobre el mismo vault;
   `strace` **no está instalado** en este entorno, así que la evidencia debe ser de contadores y
   cronómetro, no de trazas de syscalls.

**Tests actuales que deben seguir verdes** (ninguno mide el rendimiento del borrado):

| Test | Cubre |
| --- | --- |
| `int_uninstall_backup.rs::partial_desinstall_names_the_backup_dir:13-62` | backup con nombre tras borrado parcial |
| `e2e_maintenance.rs::uninstall_removes_the_three_scopes_and_keeps_the_notes:480-559` | los 3 scopes; notas intactas |
| `e2e_maintenance.rs::uninstall_backup_dir_is_private_to_the_user:563-584` | privacidad del backup |
| `e2e_maintenance.rs::uninstall_without_scopes_is_noop_ok:587-604` | sin scopes ⇒ noop |
| `e2e_maintenance.rs::second_uninstall_is_a_noop:607-625` | segundo desinstall idempotente |

**ADR: no necesario.** Es un detalle de implementación (primitiva de borrado y paralelismo), sin
cambio de contrato MCP ni de las decisiones D1-D8; no se re-editan ADRs Accepted. Registrar en
`docs/BACKLOG.md` §8.

## Workarounds

> ⚠️ **WORKAROUND** (hasta aplicar el fix)
>
> Dejar que H8 termine: el proceso está haciendo trabajo de FS, no colgado. No interrumpir a mitad,
> porque un borrado parcial deja el payload incompleto y el panel informa del backup con nombre
> (`maintenance.rs:227-237`); en ese caso repetir el desinstall (segunda pasada noop,
> `e2e_maintenance.rs:607-625`). No sustituir el borrado por un `rm -rf` manual: la regla del repo
> exige `just clean` para borrados acotados y el backup debe crearse primero
> (`maintenance.rs:220-225`).

## Recurrences

| Date | Similar Issue | Variation |
| --- | --- | --- |
| 2026-11-25 | H8 lento en `desinstall` | ~4 m 21 s por `remove_dir_all` sobre 101.413 entradas en fuseblk/NTFS-3G |

**Tercer síntoma del mismo release beta.3; los dos fallos de error del gate y F6 tienen raíz
distinta y están en [fix02](fix02-wizard-gate-modelinvalid-y-f6-silencioso.md).**

## References

- Borrado y scopes: `crates/tepochcalli/src/application/maintenance.rs:47,52-57,220-245,262-268`
- Backup `copy_tree` y privacidad: `crates/tepochcalli/src/application/maintenance.rs:277-303,331-368`
- Pausa de la TUI: `crates/tepochcalli/src/adapters/ui_ratatui.rs:349-359`
- Medición del venv (reporte del dueño, 2026-11-25): `obsidian-workspace/.tepochcalli/venv` — 2,1 G, 51.386 entradas
- Tests de desinstall: `crates/tepochcalli/tests/int_uninstall_backup.rs`, `crates/tepochcalli/tests/e2e_maintenance.rs`
- Diagnóstico hermano (mismo release beta.3, raíz distinta): [fix02-wizard-gate-modelinvalid-y-f6-silencioso.md](fix02-wizard-gate-modelinvalid-y-f6-silencioso.md)

---

**Diagnosis created by `/diagnosis`. Update this file if the fix reveals additional insights.**
