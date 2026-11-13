# Evidencia de aceptación (Phase 6 — E2E Acceptance)

Evidencia **medida** de la aceptación E2E de los 7 criterios de [UH.md](../UH.md): qué se midió,
con qué método, sobre qué host y con qué resultado. Cada cifra lleva su comando; la que no se
midió se declara como tal.

**No es un diagnóstico.** Un diagnóstico ([`docs/diagnosis/`](../diagnosis/README.md)) explica la
causa raíz de un issue; aquí se publica evidencia de aceptación, aunque en el camino aparezca un
hallazgo que acabe como deuda.

**Jerarquía de evidencia (D8):** `medido > estimado > declarado`. Se publica lo medido con su
método; lo estimado y lo declarado se etiquetan y nunca se presentan como medición.

| Fichero | Qué contiene | Criterios de UH.md |
| --- | --- | --- |
| [protocol.md](protocol.md) | Protocolo y umbrales: host de referencia, filesystem de contraste, huecos por criterio, gate D9 | 1-7 (base de todos) + gate D9 |
| [corpus.md](corpus.md) | Corpus de escala 10 000 notas + 1 000 PDFs, con manifiesto de hashes reproducible | 6 |
| [documents.md](documents.md) | Coste real de extraer documentos binarios con markitdown (PDF de 30/335/1 313 páginas) | 2 y 7 |
| [payload-refs.md](payload-refs.md) | Auditoría de las 111 refs del payload a skills/agentes (0 huérfanas) | 1 + gate D9 |
| [search-scale.md](search-scale.md) | `search` a escala 10k/1k (p95) y deriva del índice FTS ES/EN | 3 y 6 |
| [scale-ratio.md](scale-ratio.md) | Brazos 10 % vs 100 %: Δ de indexación y `search` (ratio vs cota 2×), walk-only y límite fuseblk/NTFS-3G | 6 (+2 y 3) |
| [token-budget.md](token-budget.md) | Tokens por consulta con tokenizador real: payload del server (estimador vs real) y total e2e con la respuesta citada | 4 |
| [citations.md](citations.md) | Identidad F1 re-verificada contra el archivo vivo (`verify.py --spot-check`): tasa de citas reproducibles, par exit 0/≠0 y solo lectura de `db/` | 5 |
| [format-matrix.md](format-matrix.md) | Matriz ejecutable de 9 formatos (índice vs conversor) con `doc_kind`/`offsets_ref`/indexabilidad/`source_path`, la distinción `written_to` vs cita, y los GAP con su mensaje real (`.doc`, `.ppt`, PDF escaneado, `url` sin egress) | 7 |

Si llega otra fase de aceptación, este directorio se parte en subcarpetas `acceptance/phaseN/` para no mezclar evidencias.

El protocolo de método y umbrales vive también en [TRD.md](../TRD.md) §6.1-§6.2 y la metodología
de la corrida en [WORKFLOW.md](../WORKFLOW.md) §Phase 6.
