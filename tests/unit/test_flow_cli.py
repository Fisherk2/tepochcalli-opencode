"""CLI `python -m tepochcalli_flow` (T12, D24): `refresh` + `embed-check`.

Contrato JSON (lo consume el wizard vía `CommandRunner`, stdout parseable):

* `refresh` → `{"scanned": N, "indexed": N, "skipped": N, "elapsed_ms": N}`
* `embed-check --model <id>` → `{"ok": true, "model": id, "dims": N,
  "rss_peak_bytes": N}` o `{"ok": false, "model": id,
  "error_code": "E_MODEL_INVALID", "detail": ...}`

Los tests NO descargan modelos ni tocan la red: la factoria del embedder y el
`refresh` se sustituyen por fakes. La diferencia de plataforma del RSS (OM-6:
Linux informa KB, macOS bytes) se pina con un test por rama.
"""

from __future__ import annotations

import json
import sys

import pytest
import tepochcalli_flow.__main__ as cli


def test_refresh_prints_report_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`refresh` imprime el `RefreshReport` como JSON plano en stdout (D24)."""
    monkeypatch.setattr(
        cli, "run_refresh", lambda: {"scanned": 2, "indexed": 2, "skipped": 0, "elapsed_ms": 7}
    )
    assert cli.main(["refresh"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"scanned": 2, "indexed": 2, "skipped": 0, "elapsed_ms": 7}


def test_embed_check_ok_reports_dims_and_rss(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`embed-check` con modelo sano informa `dims` y el RSS pico en BYTES."""

    class _FakeEmbedder:
        def encode(self, _text: str) -> list[float]:
            return [0.1] * 384

    monkeypatch.setattr(cli, "build_embedder_for_model", lambda _model: _FakeEmbedder())
    monkeypatch.setattr(cli, "rss_peak_bytes", lambda: 1_234_567)
    assert cli.main(["embed-check", "--model", "paraphrase-multilingual-MiniLM-L12-v2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
        "dims": 384,
        "rss_peak_bytes": 1_234_567,
    }


def test_embed_check_bad_model_reports_e_model_invalid(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un repo que no es de embeddings ⇒ `ok: false` con `E_MODEL_INVALID`."""
    monkeypatch.setattr(cli, "CONTROL_PHRASE", "tepochcalli embedding check")

    def _boom(_model: str) -> object:
        raise ValueError("not a sentence-transformers repo")

    monkeypatch.setattr(cli, "build_embedder_for_model", _boom)
    assert cli.main(["embed-check", "--model", "gpt2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["model"] == "gpt2"
    assert payload["error_code"] == "E_MODEL_INVALID"


def test_embed_check_uses_control_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    """La frase de control es la del AC, no un texto cualquiera."""
    seen: list[str] = []

    class _FakeEmbedder:
        def encode(self, text: str) -> list[float]:
            seen.append(text)
            return [0.0] * 8

    monkeypatch.setattr(cli, "build_embedder_for_model", lambda _model: _FakeEmbedder())
    monkeypatch.setattr(cli, "rss_peak_bytes", lambda: 0)
    assert cli.cmd_embed_check("some-model")["ok"] is True
    assert seen == ["tepochcalli embedding check"]


def test_rss_peak_bytes_linux_scales_kb_to_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """OM-6: en Linux `ru_maxrss` viene en KB ⇒ se normaliza a bytes."""

    class _Usage:
        ru_maxrss = 1024

    import resource

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(resource, "getrusage", lambda _who: _Usage())
    assert cli.rss_peak_bytes() == 1024 * 1024


def test_rss_peak_bytes_macos_is_already_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """OM-6: en macOS `ru_maxrss` ya viene en bytes ⇒ no se escala."""

    class _Usage:
        ru_maxrss = 1024

    import resource

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(resource, "getrusage", lambda _who: _Usage())
    assert cli.rss_peak_bytes() == 1024
