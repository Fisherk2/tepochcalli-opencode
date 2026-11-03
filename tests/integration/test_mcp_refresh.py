"""T3: `index_refresh` end-to-end — ciclo Δ por stdio, candado y cero red (plan §6).

Fuentes de verdad:

* tasks/plan.md §6 T3 AC — `asdict(RefreshReport)` tal cual con el orden exacto;
  `locked:true` ⇒ tres ceros sin update; idempotencia (`indexed: 0`); canario
  cero red / cero LLM; `just quality` con Phase 1 intacta.
* specs/spec-mcp-server.md §Tool `index_refresh`.
* `tests/integration/test_delta.py` (Phase 1) — la secuencia
  crea→modifica→borra→idempotencia y las cuentas exactas que aquí se repiten
  a través de la TOOL (2 ficheros md: (2,2,0) → (3,1,2) → (3,1,2) →
  (2,0,2) → (2,0,2)).

Decisiones de test, documentadas:

* **Server como SUBPROCESO por stdio** con `TEPOCHCALLI_VAULT_ROOT` propio
  (mismo patrón que `test_mcp_server._running_server`): el environment global
  de cocoindex no admite dos vaults en el mismo proceso (sonda T9), y así la
  tool se ejercita COMO LA VE EL HARNESS.
* **Canario de cero red = `tests/support/nonet/sitecustomize.py`** inyectado
  por `PYTHONPATH` en el hijo: cualquier `connect` AF_INET/AF_INET6 LANZA
  `OSError` ⇒ el refresh respondería `INTERNAL` y todo test de éxito fallaría
  (auto-exigente). Una llamada LLM por API ES una conexión saliente, así que
  UN guard cubre «cero red y cero LLM» (patrón M3(b) de Phase 1). El modelo
  se calienta ANTES (subproceso con red permitida: en frío descarga una vez;
  después `HF_HUB_OFFLINE=1` + canario).
* **Dos pruebas de candado, qué hace cada una** (reparto del AC de T3):
  1. `test_retained_lock…` DETERMINISTA (un hijo) — **el ancla del AC**: el
     padre retiene el flock mientras el server hijo intenta el refresh;
     asserta `locked:true`, tres ceros y snapshot byte a byte de `db/` SIN
     escrituras (mecánica idéntica al test de candado de Phase 1, ejercitando
     la tool). La prohibición de doble escritura y el `locked:true` viven AQUÍ
     y no pueden parpadear.
  2. `test_two_concurrent_refreshes_both_yield_locked…` — DOS sesiones stdio
     simultáneas (`asyncio.gather`) contra el candado RETENIDO POR EL PADRE:
     ambas deben responder `locked:true` con ceros y sin escribir. La
     superposición la garantiza el `flock` del kernel, no el reloj.
     **Historia (rework tras el gate del lead):** la versión original exigía
     «exactamente UNO locked» entre dos hijos RACING — eso presupone que sus
     updates se solapan en el tiempo, cosa que ni el contrato ni el scheduler
     garantizan; en el gate independiente falló con `(2,0,2)/(2,0,2)` (sin
     solapamiento: ambos unlocked). Ninguna aserción de esta suite depende ya
     del reloj: la raca de reloj se retiró, la vista CONCURRENTE se conserva
     con el candado del padre como garantía determinista.
* El `journey` (5 pasos en UNA sesión) mantiene el server vivo entre llamadas
  — la carga del modelo se amortiza y los mtime/Δ los ve el hijo, no el padre.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp import ClientSession
from support.mcp_server import running_server, server_env, warm_model
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation
from tepochcalli_mcp import errors

REPORT_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms", "locked", "roots"]
"""Orden exacto de `asdict(RefreshReport)` — contrato §Tool `index_refresh`."""

ALPHA = (
    "# Alpha — notas iniciales\n\n"
    "Primer fichero del vault T3: dos párrafos de prosa para que el segmentador "
    "produzca chunks con cita completa y el ciclo delta tenga algo que indexar.\n\n"
    "## Sección beta\n\n"
    "Segundo párrafo de alpha con métricas, cohorte y seguimiento de referencia.\n"
)
ALPHA_V2 = (
    "# Alpha — versión modificada\n\n"
    "Reescrito por el paso `modify` del journey T3: el delta debe reescribir SOLO "
    "los chunks de alpha y contar exactamente un archivo indexado.\n"
)
BETA = (
    "# Beta — segunda nota\n\n"
    "Fichero estable del vault T3: no se toca en ningún paso, así que siempre "
    "aparece como skipped una vez indexado.\n"
)
GAMMA = (
    "# Gamma — nota añadida\n\n"
    "Creado en el paso `add` y borrado en el paso `delete`: un archivo que entra "
    "y sale del índice dentro del mismo journey.\n"
)


async def _call_refresh(session: ClientSession) -> dict[str, object]:
    """`index_refresh` por stdio: payload parseado con el orden exacto del contrato."""
    result = await session.call_tool("index_refresh", {})
    assert not result.is_error, f"index_refresh falló (¿red? ¿guard?): {result.content[0].text}"
    report = json.loads(result.content[0].text)
    assert list(report) == REPORT_FIELDS, list(report)
    return report


async def _call_refresh_raw(session: ClientSession) -> tuple[bool, dict[str, object]]:
    """`index_refresh()` por stdio sin argumentos: `(is_error, payload)` sin exigir éxito."""
    result = await session.call_tool("index_refresh", {})
    return bool(result.is_error), json.loads(result.content[0].text)


def _counts(report: dict[str, object]) -> tuple[int, int, int]:
    """Devuelve `(scanned, indexed, skipped)` — la tripleta exacta de Phase 1."""
    return (report["scanned"], report["indexed"], report["skipped"])  # type: ignore[return-value]


def _assert_contract(report: dict[str, object]) -> None:
    """Orden exacto, tipos y la identidad `scanned == indexed + skipped` (Phase 1)."""
    assert list(report) == REPORT_FIELDS, list(report)
    scanned, indexed, skipped = _counts(report)
    assert isinstance(scanned, int) and isinstance(indexed, int) and isinstance(skipped, int)
    assert scanned == indexed + skipped, report
    assert isinstance(report["locked"], bool)
    assert isinstance(report["elapsed_ms"], int) and report["elapsed_ms"] >= 0


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int | None]]:
    """`(mtime_ns, size)` por ruta relativa — detecta cualquier escritura."""
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): (
            path.stat().st_mtime_ns,
            path.stat().st_size if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture(scope="module")
def refresh_vault(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Vault T3 de 2 ficheros md con el modelo calentado, SIN indexar.

    El primer refresh del journey lo hace la TOOL, como en producción.
    """
    vault = tmp_path_factory.mktemp("vault-t3")
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir(parents=True)
    (resources / "alpha.md").write_text(ALPHA, encoding="utf-8")
    (resources / "beta.md").write_text(BETA, encoding="utf-8")

    models_link = warm_model(vault)
    return vault, models_link


# --- journey: crea → modifica → borra → idempotencia (5 pasos, 1 sesión) -----------


def test_journey_creates_modifies_deletes_and_stays_idempotent(
    refresh_vault: tuple[Path, Path],
) -> None:
    """Secuencia completa a través de la tool con las cuentas exactas de Phase 1."""
    vault, models_link = refresh_vault
    resources = vault / citation.RESOURCES_DIR
    env = server_env(vault, models_link)

    async def journey() -> list[dict[str, object]]:
        reports: list[dict[str, object]] = []
        async with running_server(env) as session:
            reports.append(await _call_refresh(session))  # initial: indexa los 2 ficheros
            (resources / "gamma.md").write_text(GAMMA, encoding="utf-8")
            reports.append(await _call_refresh(session))  # add
            (resources / "alpha.md").write_text(ALPHA_V2, encoding="utf-8")
            reports.append(await _call_refresh(session))  # modify
            (resources / "gamma.md").unlink()
            reports.append(await _call_refresh(session))  # delete
            reports.append(await _call_refresh(session))  # idempotent
        return reports

    initial, added, modified, deleted, idempotent = asyncio.run(journey())

    for report in (initial, added, modified, deleted, idempotent):
        _assert_contract(report)
        assert report["locked"] is False

    assert _counts(initial) == (2, 2, 0), "el primer refresh de la tool indexa los 2 md"
    assert _counts(added) == (3, 1, 2), "add: SOLO gamma se (re)escribe"
    assert _counts(modified) == (3, 1, 2), "modify: SOLO alpha se reescribe"
    assert _counts(deleted) == (2, 0, 2), "borrados NO cuentan (RefreshReport §doc)"
    assert idempotent["indexed"] == 0, "2ª pasada sin cambios: indexed 0 (idempotencia)"
    assert idempotent["scanned"] == idempotent["skipped"]


# --- candado 1/2: retención DETERMINISTA en el padre ---------------------------------


def test_retained_lock_returns_zeros_and_writes_nothing(
    refresh_vault: tuple[Path, Path],
) -> None:
    """DETERMINISTA: el padre retiene el flock ⇒ la tool responde `locked:true`.

    Cubre el AC «locked ⇒ sin update y tres ceros» SIN depender de carreras:
    snapshot byte a byte de `.tepochcalli/db/` antes/después demuestra que el
    refresh bloqueado no escribió nada (misma mecánica que el test de candado
    de Phase 1, ahora ejercitando `index_refresh` por stdio).
    """
    vault, models_link = refresh_vault
    lock_fd = flow_app._acquire_refresh_lock(vault)
    assert lock_fd is not None, "nadie retenía el candado: el acquire debe triunfar"
    try:
        db_snapshot = _tree_snapshot(vault / ".tepochcalli" / "db")
        env = server_env(vault, models_link)

        async def locked_call() -> dict[str, object]:
            async with running_server(env) as session:
                return await _call_refresh(session)

        report = asyncio.run(locked_call())
    finally:
        flow_app._release_refresh_lock(lock_fd)

    _assert_contract(report)
    assert report["locked"] is True
    assert _counts(report) == (0, 0, 0), "refresh bloqueado: cero en las tres cuentas"
    assert _tree_snapshot(vault / ".tepochcalli" / "db") == db_snapshot, (
        "el refresh bloqueado NO debe escribir ni un byte en db/"
    )


# --- candado 2/2: concurrencia SIN reloj (determinista) -------------------------------------


def test_two_concurrent_refreshes_both_yield_locked_and_write_nothing(
    refresh_vault: tuple[Path, Path],
) -> None:
    """Vista CONCURRENTE determinista: DOS sesiones a la vez contra el candado retenido.

    El padre retiene el `flock` (`flow_app._acquire_refresh_lock`) ANTES de
    lanzar las dos sesiones y solo lo suelta tras recibir ambas respuestas:
    que los hijos se superpongan o no en el tiempo deja de importar — el
    kernel garantiza que NINGUNO puede adquirir, así que siempre, en cualquier
    máquina, las dos respuestas son `locked:true` con tres ceros y `db/` queda
    byte a byte intacto. Cero aserciones condicionadas al solapamiento.

    **Por qué no «exactamente uno locked»** (rework tras el gate): esa forma
    era una carrera de reloj — exige que los updates de los dos hijos se
    solapen; con un vault totalmente memoizado el segundo entró cuando el
    primero ya había soltado el candado (`(2,0,2)/(2,0,2)`, 1 failed en la
    corrida independiente). Un flake en la suite de corrección es peor que un
    test que no existe.

    **Reparto del AC de T3:** la prohibición de doble escritura y el
    `locked:true ⇒ tres ceros` los carga `test_retained_lock_returns_zeros_and_
    writes_nothing` (el ancla determinista, sin concurrencia); ESTE test añade
    la vista de DOS sesiones stdio simultáneas sobre el mismo vault/candado —
    aislamiento entre sesiones, contrato completo en ambas respuestas y cero
    escrituras mientras alguien retiene. El journey carga cuentas e
    idempotencia.
    """
    vault, models_link = refresh_vault
    lock_fd = flow_app._acquire_refresh_lock(vault)
    assert lock_fd is not None, "nadie retenía el candado: el acquire debe triunfar"
    try:
        db_snapshot = _tree_snapshot(vault / ".tepochcalli" / "db")
        env = server_env(vault, models_link)

        async def both() -> list[dict[str, object]]:
            async with running_server(env) as first, running_server(env) as second:
                return list(await asyncio.gather(_call_refresh(first), _call_refresh(second)))

        first_report, second_report = asyncio.run(both())
    finally:
        flow_app._release_refresh_lock(lock_fd)

    for report in (first_report, second_report):
        _assert_contract(report)
        assert report["locked"] is True, "el flock del padre es kernel: nadie puede adquirir"
        assert _counts(report) == (0, 0, 0), "refresh bloqueado: cero en las tres cuentas"
    assert _tree_snapshot(vault / ".tepochcalli" / "db") == db_snapshot, (
        "ninguna de las dos sesiones escribió en db/ mientras el padre retenía"
    )


# --- higiene del payload -------------------------------------------------------------------------


def test_payload_db_and_models_are_never_created_by_the_tool() -> None:
    """Ningún refresh de este módulo materializa `db/` ni `models/` en el payload."""
    payload = Path(__file__).parents[2] / "obsidian-workspace" / ".tepochcalli"
    assert not (payload / "db").exists()
    assert not (payload / "models").exists()


# --- T6: la ruta litellm del refresh ------------------------------------------------------


def test_refresh_without_api_key_for_litellm_reports_e_api_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config `litellm` SIN la clave ⇒ `E_API_AUTH` canónico — sin red, sin valor de clave.

    El flow falla en SU fábrica con el error tipado de clave ausente ANTES de
    cualquier llamada a la API (chequeo local de `api_key_env`);
    `server._refresh_once` lo traduce a la excepción de dominio del server y
    `index_refresh` responde el dialecto `E_*`. El hijo corre con el canario
    `nonet` de este módulo: cualquier dial real lo convertiría en `INTERNAL`
    y el test fallaría solo (auto-exigente).
    """
    config_dir = tmp_path / ".tepochcalli" / "config"
    config_dir.mkdir(parents=True)
    (tmp_path / citation.RESOURCES_DIR).mkdir()  # el default exige la raíz (T8)
    (config_dir / "tepochcalli.toml").write_text(
        '[embedding]\nprovider = "litellm"\nmodel = "openai/text-embedding-3-small"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("TEPOCHCALLI_EMBED_API_KEY", raising=False)
    env = server_env(tmp_path)

    async def go() -> dict[str, object]:
        async with running_server(env) as session:
            result = await session.call_tool("index_refresh", {})
            assert result.is_error, "sin clave debe responder un error canónico, no un reporte"
            return json.loads(result.content[0].text)

    payload = asyncio.run(go())

    error = payload["error"]
    assert list(error) == ["code", "message", "fix_hint"]
    assert error["code"] == "E_API_AUTH"
    assert "TEPOCHCALLI_EMBED_API_KEY" in error["message"], "nombra la variable, no un valor"
    assert error["fix_hint"] == errors.FIX_API_AUTH
    assert "sk-" not in json.dumps(payload)


# --- raíces: SOLO las declaradas por el usuario en `INDEXER_DIR` (D42/D44/D65/D67) ----------


def test_indexer_dir_indexes_two_roots_recursively_and_reports_them(tmp_path: Path) -> None:
    """Dos raíces en `INDEXER_DIR` ⇒ se indexan ambas; `roots` y `rag_status` las declaran."""
    (tmp_path / citation.RESOURCES_DIR).mkdir()
    (tmp_path / citation.RESOURCES_DIR / "nota.md").write_text(
        "# Nota por omisión\n\nNo entra: `INDEXER_DIR` declara otras raíces.\n", encoding="utf-8"
    )
    (tmp_path / "materiales" / "1-geografia").mkdir(parents=True)
    (tmp_path / "materiales" / "1-geografia" / "clima.md").write_text(
        "# Clima\n\nLa aridez del altiplano condiciona el calendario agrícola.\n", encoding="utf-8"
    )
    (tmp_path / "documentos" / "pdf").mkdir(parents=True)
    (tmp_path / "documentos" / "pdf" / "articulo.md").write_text(
        "# Artículo\n\nTexto bajo documentos/pdf: la recursión debe alcanzarlo.\n", encoding="utf-8"
    )
    models_link = warm_model(tmp_path)
    env = {**server_env(tmp_path, models_link), "INDEXER_DIR": "materiales,documentos"}

    async def go() -> tuple[dict[str, object], dict]:
        async with running_server(env) as session:
            report = await _call_refresh(session)
            result = await session.call_tool("rag_status", {})
            assert not result.is_error, result.content[0].text
            return report, json.loads(result.content[0].text)

    report, status = asyncio.run(go())

    _assert_contract(report)
    assert report["roots"] == ["materiales", "documentos"]
    assert _counts(report) == (2, 2, 0), "solo las dos raíces declaradas (00-Resources queda fuera)"
    assert status["index"]["last_refresh_roots"] == ["materiales", "documentos"]
    assert status["index"]["available_roots"] == ["00-Resources", "documentos", "materiales"]


def test_indexer_dir_env_supplies_the_default_roots(tmp_path: Path) -> None:
    """`INDEXER_DIR` de `opencode.json` ⇒ `index_refresh()` sin argumentos indexa esas raíces.

    La declaración vive en el entorno del proceso (string→string, multi-valor
    por comas), no en el toml ni en un argumento de la llamada.
    """
    (tmp_path / "materiales").mkdir()
    (tmp_path / "documentos").mkdir()
    (tmp_path / "materiales" / "clima.md").write_text(
        "# Clima\n\nLa aridez del altiplano condiciona el calendario agrícola.\n", encoding="utf-8"
    )
    (tmp_path / "documentos" / "articulo.md").write_text(
        "# Artículo\n\nTexto bajo documentos: debe entrar por `INDEXER_DIR`.\n", encoding="utf-8"
    )
    models_link = warm_model(tmp_path)
    env = {**server_env(tmp_path, models_link), "INDEXER_DIR": "materiales,documentos"}

    async def go() -> dict[str, object]:
        async with running_server(env) as session:
            return await _call_refresh(session)

    report = asyncio.run(go())

    _assert_contract(report)
    assert report["roots"] == ["materiales", "documentos"]
    assert _counts(report) == (2, 2, 0), "las dos raíces del entorno, recursivas"


def test_missing_root_in_indexer_dir_is_validation_error_and_indexes_nothing(
    tmp_path: Path,
) -> None:
    """Raíz inexistente en `INDEXER_DIR` ⇒ `VALIDATION_ERROR` (nunca `INTERNAL`), cero filas.

    Sin modelo: el borde corre antes que `E_NO_EMBEDDER` y antes que el motor,
    así que el pool de modelos no se toca (el canario `nonet` lo confirma) y no
    se crea `db/` — cero filas nuevas.
    """
    (tmp_path / "materiales").mkdir()
    (tmp_path / "documentos").mkdir()
    (tmp_path / "materiales" / "x.md").write_text("# X\n\nMaterial existente.\n", encoding="utf-8")
    env = {**server_env(tmp_path), "INDEXER_DIR": "materiales,Documentos"}

    async def go() -> tuple[bool, dict[str, object]]:
        async with running_server(env) as session:
            return await _call_refresh_raw(session)

    is_error, payload = asyncio.run(go())

    assert is_error is True
    error = payload["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == {
        "requested": "Documentos",
        "exists": False,
        "suggestions": ["documentos"],
        "vault_dirs": ["documentos", "materiales"],
    }
    assert not (tmp_path / ".tepochcalli" / "db").exists(), (
        "fail-fast atómico: una raíz mala no deja media indexación hecha"
    )


def test_empty_directory_is_not_an_error(tmp_path: Path) -> None:
    """Directorio vacío ⇒ `ok` con `scanned: 0` — el agente no lo lee como fallo."""
    (tmp_path / citation.RESOURCES_DIR).mkdir()
    models_link = warm_model(tmp_path)
    env = server_env(tmp_path, models_link)

    async def go() -> dict[str, object]:
        async with running_server(env) as session:
            return await _call_refresh(session)

    report = asyncio.run(go())

    _assert_contract(report)
    assert _counts(report) == (0, 0, 0)
    assert report["roots"] == [citation.RESOURCES_DIR]
