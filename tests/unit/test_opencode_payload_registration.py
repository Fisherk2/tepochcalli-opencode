"""Registro T9 en `obsidian-workspace/opencode.json` con merge conservador (D-d, plan §6).

Tres afirmaciones graduadas por el AC de T9:

1. El payload sigue **parseable** y las dos entradas gestionadas tienen la
   forma EXACTA del contrato (`tepochcalli-rag` con `type/command/cwd/
   environment`, `markitdown` con su `command`) — forma `python -m`, nunca
   console script (D17: el bit de ejecución se pierde en NTFS/fuseblk).
2. `excel` y `jupyter` (existentes, ambas `disabled: true`) quedan intactas.
3. **Merge conservador demostrado, no afirmado:** al quitar SOLO las dos
   entradas gestionadas, el resto del documento re-serializado con el MISMO
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

# Forma exacta del AC de T9 (spec-markitdown §Config es la fuente de la
# entrada `markitdown`; `disabled: false` explícito, como en ese jsonc).
TPOCHCALLI_RAG_ENTRY = {
    "type": "local",
    "command": [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"],
    "cwd": ".",
    "environment": {"TEPOCHCALLI_ROOT": "."},
    "disabled": False,
}
MARKITDOWN_ENTRY = {
    "type": "local",
    "command": [".tepochcalli/venv/bin/python", "-m", "markitdown_mcp"],
    "disabled": False,
}
MANAGED_KEYS = ("tepochcalli-rag", "markitdown")


def test_payload_is_parseable_and_the_two_entries_have_the_exact_shape() -> None:
    """El JSON parsea y las dos entradas gestionadas tienen la forma exacta del AC."""
    data = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))
    servers = data["mcp"]["servers"]

    assert servers["tepochcalli-rag"] == TPOCHCALLI_RAG_ENTRY, "forma exacta de tepochcalli-rag"
    assert servers["markitdown"] == MARKITDOWN_ENTRY, "forma exacta de markitdown"
    # D17: forma `python -m`, jamás el console script venv/bin/tepochcalli-mcp.
    assert TPOCHCALLI_RAG_ENTRY["command"][1] == "-m"
    assert MARKITDOWN_ENTRY["command"][1] == "-m"
    # Las entradas preexistentes conservan su estado (una está disabled: true).
    assert servers["excel"]["disabled"] is True
    assert servers["jupyter"]["disabled"] is True


def test_the_rest_of_the_json_is_byte_identical_to_the_original() -> None:
    """Quitando SOLO las entradas gestionadas, el resto es byte-idéntico al original."""
    current = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL_JSON.read_text(encoding="utf-8"))

    for key in MANAGED_KEYS:
        del current["mcp"]["servers"][key]

    # Mismo serializador a ambos lados: compara estructura Y orden de claves;
    # un diff aquí = el merge tocó algo que no debía (D-d).
    assert json.dumps(current, indent=2, ensure_ascii=False) == json.dumps(
        original, indent=2, ensure_ascii=False
    ), "el merge conservador exige que el resto del JSON quede byte-idéntico"
