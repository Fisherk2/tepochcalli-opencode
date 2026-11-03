"""Registro T9 en `obsidian-workspace/opencode.json` con merge conservador (D-d, plan §6).

Tres afirmaciones graduadas por el AC de T9 (ajustadas en la review Phase 2,
2026-10-27: el server markitdown standalone RETIRADO — la conversión en
proceso (D-b, costura `_convert_seam`) es la ÚNICA consumidora de markitdown;
la entrada de wire `mcp.servers.markitdown` era superficie sin cliente):

1. El payload sigue **parseable** y la única entrada nueva tiene la forma
   EXACTA del contrato (`tepochcalli-rag` con `type/command/cwd/environment`)
   — forma `python -m`, nunca console script (D17: el bit de ejecución se
   pierde en NTFS/fuseblk); `markitdown` ya NO debe estar registrada.
2. `excel` y `jupyter` (existentes, ambas `disabled: true`) quedan intactas.
3. **Merge conservador demostrado, no afirmado:** al quitar las entradas
   gestionadas, el resto del documento re-serializado con el MISMO
   serializador es byte-idéntico al original congelado en
   `tests/fixtures/opencode_payload_before_t9.json` (copia de
   `git show HEAD:obsidian-workspace/opencode.json` al cerrar T8). Cualquier
   cambio de clave, valor u ORDEN en el resto rompe la igualdad de bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

PAYLOAD_JSON = Path(__file__).resolve().parents[2] / "obsidian-workspace" / "opencode.json"
ORIGINAL_JSON = Path(__file__).resolve().parents[1] / "fixtures" / "opencode_payload_before_t9.json"

# Forma exacta del AC de T9 — la entrada markitdown del jsonc de spec-markitdown
# §Config quedó RETIRADA en la review Phase 2: se POPea en ambos lados del
# contrato byte-idéntico para mantener viva la afirmación del resto.
TPOCHCALLI_RAG_ENTRY = {
    "type": "local",
    "command": [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"],
    "cwd": ".",
    "environment": {"TEPOCHCALLI_ROOT": "."},
    "disabled": False,
}
# Claves gestionadas por el wizard: se POPean en AMBOS lados del contrato
# byte-idéntico para que la afirmación del merge conservador siga viva.
#  * `markitdown` (D29): retirada del payload en la review Phase 2. Sigue en la
#    tupla porque el fixture congelado es la copia PRE-T9 y todavía la contiene;
#    el POP simétrico es lo que permite comparar el resto del JSON.
#  * `anydoc` (D40/T14): el payload la trae como fallback `disabled: true`
#    (D30) y no existía en el fixture pre-T9 ⇒ sin ella en la tupla, el merge
#    parecería haber tocado una clave del usuario.
MANAGED_KEYS = ("tepochcalli-rag", "markitdown", "anydoc")


def test_payload_is_parseable_and_only_tepochcalli_rag_is_registered() -> None:
    """El JSON parsea: `tepochcalli-rag` forma exacta, `markitdown` retirada."""
    data = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))
    servers = data["mcp"]["servers"]

    assert servers["tepochcalli-rag"] == TPOCHCALLI_RAG_ENTRY, "forma exacta de tepochcalli-rag"
    assert "markitdown" not in servers, (
        "review Phase 2: sin server standalone (conversión EN PROCESO, D-b)"
    )
    # D17: forma `python -m`, jamás el console script venv/bin/tepochcalli-mcp.
    assert TPOCHCALLI_RAG_ENTRY["command"][1] == "-m"
    # Las entradas preexistentes conservan su estado (una está disabled: true).
    assert servers["excel"]["disabled"] is True
    assert servers["jupyter"]["disabled"] is True


def test_the_rest_of_the_json_is_byte_identical_to_the_original() -> None:
    """Quitando las entradas gestionadas de ambos lados, el resto es byte-idéntico.

    `markitdown` existe en el fixture congelado de T8 y NO en el payload
    actual (retirada en la review 2026-10-27): el POP simétrico mantiene la
    afirmación del merge conservador (el RESTO del JSON no se toca).
    """
    current = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL_JSON.read_text(encoding="utf-8"))

    for key in MANAGED_KEYS:
        current["mcp"]["servers"].pop(key, None)
        original["mcp"]["servers"].pop(key, None)

    # Mismo serializador a ambos lados: compara estructura Y orden de claves;
    # un diff aquí = el merge tocó algo que no debía (D-d).
    assert json.dumps(current, indent=2, ensure_ascii=False) == json.dumps(
        original, indent=2, ensure_ascii=False
    ), "el merge conservador exige que el resto del JSON quede byte-idéntico"
