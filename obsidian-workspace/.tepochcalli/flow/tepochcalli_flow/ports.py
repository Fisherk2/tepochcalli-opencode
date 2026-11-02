"""Puerto de lectura `ChunkReader`: contrato de búsqueda citada sin motor (T9).

Define la FRONTERA hexagonal de lectura detrás de la cual vive el motor
CocoIndex/LanceDB (ADR-005: «la cita precisa es estructural, no opcional»).
Phase 2 consume ESTE módulo —el server MCP `tepochcalli-rag` no vuelve a tocar
el engine— y su contrato es el congelado en specs/spec-mcp-server.md §search:

* `search(query, top_k, path_filter?)` devuelve chunks con
  `{text, source_path, heading, char_start, char_end, score}` — los seis
  campos SIEMPRE presentes (Hyrum: extensiones futuras solo aditivas).
* `heading` es nullable (D13): `None` cuando el chunk no tiene heading padre;
  el campo existe siempre, nunca se omite.
* `score` ∈ [0,1] con orden descendente garantizado (semántica exacta
  documentada en el adaptador, que es quien conoce la fórmula).
* `path_filter` es un GLOB relativo a la raíz del vault con la semántica
  `*`/`?` — la misma que Phase 2 expresará como `*`→`%` en `LIKE`
  (spec-mcp-server §search; la traducción exacta vive y se congela en
  `tepochcalli_flow.adapters.lancedb_reader.path_filter_to_like_predicate`).

Código de dominio (hexagonal: la dependencia apunta hacia dentro): sin I/O,
sin red y SIN importar el motor de indexación (`cocoindex`) ni el indexador
vectorial (`lancedb`) — el test de arquitectura (CP-B, extendido en T9) lo
verifica transitivamente sobre este módulo igual que sobre `citation` y
`config`. Un lector alternativo (pgvector, LEANN — §Escape hatch) implementa
este mismo protocolo sin que Phase 2 se entere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .config import DEFAULT_TOP_K


@dataclass(frozen=True)
class CitedChunk:
    """Un chunk devuelto por la búsqueda — la forma CONGELADA de §search.

    Los campos son exactamente los del contrato `search` de
    specs/spec-mcp-server.md §search, en ese orden; ninguno es opcional y el
    dataclass es inmutable: la cita es estructural (ADR-005).
    """

    text: str
    """Contenido exacto del chunk — idéntico al rango que citan sus offsets (F1)."""

    source_path: str
    """Cita POSIX relativa al vault (`00-Resources/nota.md`, `materiales/a.pdf`; D41)."""

    heading: str | None
    """Último heading ATX previo; `None` sin padre — presente SIEMPRE (nullable, D13)."""

    char_start: int
    """Offset de carácter inicio dentro del texto extraído (no nulo; identidad F1)."""

    char_end: int
    """Offset de carácter fin exclusivo (no nulo): el slice reproduce `text` (F1)."""

    score: float
    """Relevancia híbrida normalizada a [0,1], orden descendente (§search)."""

    offsets_ref: str = "source"
    """Espacio de coordenadas de los offsets (decisión T7, congelada): `"source"`
    cuando el slice del archivo ORIGINAL reproduce `text` (md/markdown/txt) y
    `"extract"` cuando citan el markdown que Docling extrajo del PDF (el
    binario jamás es el espacio de cita). Campo ADITIVO (Hyrum, §search):
    extensiones futuras del contrato solo agregan campos, nunca retiran."""


@runtime_checkable
class ChunkReader(Protocol):
    """Puerto de lectura de chunks citados detrás del cual vive el motor (ADR-005).

    Implementado por `tepochcalli_flow.adapters.lancedb_reader.LanceDBChunkReader`
    (Phase 1) y consumido por el server MCP `tepochcalli-rag` (Phase 2). Un
    protocolo —no una clase base— porque el contrato es la SIGNATURA y la
    forma del resultado; el motor de indexación es un detalle del adaptador
    (spec-rag-engine §Escape hatch: LEANN/pgvector implementan esto mismo).
    """

    async def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        path_filter: str | None = None,
    ) -> list[CitedChunk]:
        """Devuelve los `top_k` chunks más relevantes para `query`, descendente.

        `query` es texto libre (se vectoriza y se busca léxicamente: híbrido
        ANN+FTS). `path_filter` es un glob relativo a la raíz del vault
        (`00-Resources/sub/**/*.md`, `materiales/**`); `None` busca en todo el
        índice. Lanza `ValueError` en el borde (consulta vacía, `top_k < 1`,
        glob absoluto o con `..`) — nunca devuelve forma parcial: los seis
        campos de cada chunk están siempre presentes (ADR-005).
        """
        ...
