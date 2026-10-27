"""T2: validación de rutas en el borde MCP — glob de `search` y `subdir` de `add_source`.

Fuentes de verdad:

* SPEC.md §Boundaries — «validar entradas en el borde MCP (`add_source` rutas)».
* tasks/plan.md §5 — `path_filter` absoluto o con `..` → `VALIDATION_ERROR`;
  `subdir` normalizado, sin `..`, sin absolutos, destino siempre dentro de
  `00-Resources/`, por omisión `_inbox` (T5).
* specs/spec-mcp-server.md §Security — path traversal → `VALIDATION_ERROR`.

Decisión documentada: ESTE módulo valida la forma del glob (relativo, sin `..`)
en el borde del server, pero NO lo traduce a SQL — la traducción `*`→`%` vive
y se congela en `tepochcalli_flow.adapters.lancedb_reader.
path_filter_to_like_predicate` y el adaptador la aplica (importarla aquí
arrastraría `lancedb` al paquete del server; test de arquitectura). El
adaptador además re-valida en su propio borde: defensa en profundidad, sin
duplicar la traducción.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tepochcalli_mcp import paths

# --- path_filter (glob relativo al vault) ---------------------------------------


def test_none_is_a_valid_path_filter() -> None:
    """Sin filtro busca en todo el índice: `None` es válido y se devuelve tal cual."""
    assert paths.validate_path_filter(None) is None


@pytest.mark.parametrize(
    "glob",
    [
        "00-Resources/*.md",
        "00-Resources/sub/*",
        "00-Resources/lit-pediatría/**/*.pdf",
        "00-Resources/con_guion_bajo.md",
        "00-Resources/?.md",
        "00-Resources/ñ-日.md",
    ],
)
def test_relative_globs_under_resources_are_accepted(glob: str) -> None:
    """Globs relativos multibyte incluidos: se aceptan sin tocarlos (semántica del adaptador)."""
    assert paths.validate_path_filter(glob) == glob


@pytest.mark.parametrize(
    "glob",
    [
        "/absoluto/*.md",
        "00-Resources/../secreto/*.md",
        "00-Resources\\..\\secreto\\*.md",  # backslash normalizado: mismo rechazo
        "../fuera-del-vault.md",
        "sub/../../etc/passwd",
    ],
)
def test_absolute_or_traversal_globs_are_rejected(glob: str) -> None:
    """Absoluto o con `..` → `ValueError`; el handler lo mapea a `VALIDATION_ERROR`."""
    with pytest.raises(ValueError):
        paths.validate_path_filter(glob)


def test_empty_glob_is_rejected_as_well() -> None:
    """Un glob vacío no filtra nada y no es una ruta: se rechaza en el borde."""
    with pytest.raises(ValueError):
        paths.validate_path_filter("")


# --- subdir (add_source, T5 sobre esta base) -------------------------------------


def test_missing_subdir_defaults_to_inbox() -> None:
    """`None`, vacío o en blanco → `_inbox` (destino canónico del plan §add_source)."""
    assert paths.validate_subdir(None) == paths.DEFAULT_SUBDIR
    assert paths.validate_subdir("") == paths.DEFAULT_SUBDIR
    assert paths.validate_subdir("   ") == paths.DEFAULT_SUBDIR


@pytest.mark.parametrize(
    ("given", "normalized"),
    [
        ("lit", "lit"),
        ("lit-pediatría", "lit-pediatría"),
        ("lit/pediatría", "lit/pediatría"),
        ("./lit/", "lit"),
        ("lit\\pediatría", "lit/pediatría"),  # backslash → POSIX (D9.1)
        ("ñ-日", "ñ-日"),
    ],
)
def test_subdir_is_normalized_to_a_relative_posix_path(given: str, normalized: str) -> None:
    """`subdir` queda relativo, POSIX y sin segmentos vacíos (D9.1)."""
    assert paths.validate_subdir(given) == normalized


@pytest.mark.parametrize(
    "subdir",
    [
        "/absoluto",
        "../fuera",
        "lit/../../fuera",
        "lit\\..\\fuera",
    ],
)
def test_subdir_that_escapes_resources_is_rejected(subdir: str) -> None:
    """Absoluto o `..` → `ValueError`: jamás se escribe fuera de `00-Resources/` (D9.1)."""
    with pytest.raises(ValueError):
        paths.validate_subdir(subdir)


def test_subdir_root_is_canonicalized_to_the_default() -> None:
    """`00-Resources` o `.` caen al default: no son un subdirectorio del recurso."""
    assert paths.validate_subdir(".") == paths.DEFAULT_SUBDIR
    assert paths.validate_subdir("00-Resources/") == paths.DEFAULT_SUBDIR


def test_validated_subdir_joins_resources_dir() -> None:
    """La helper de destino compone `00-Resources/<subdir>` sin duplicar prefijo."""
    assert str(paths.resources_destination("lit")) == "00-Resources/lit"
    assert str(paths.resources_destination(None)) == "00-Resources/_inbox"


# --- slug y colisión del nombre de archivo (T5) -----------------------------------


@pytest.mark.parametrize(
    ("uri", "slug"),
    [
        ("https://example.org/papers/ruiz-2024.pdf", "ruiz-2024"),
        ("https://example.org/papers/ruiz%20final.pdf", "ruiz-final"),
        ("file:///vault/staging/Informe Anual.docx", "informe-anual"),
        ("file:///vault/staging/notas.md", "notas"),
        ("https://example.org/papers/ñ-日.pdf", "ñ-日"),  # alnum multibyte se conserva
        ("https://example.org/", "example-org"),  # sin segmento: hostname
        ("file:///", "source"),  # sin hostname ni segmento: fallback
    ],
)
def test_slugify_uri_derives_the_filename_stem(uri: str, slug: str) -> None:
    """El slug sale del ÚLTIMO segmento sin extensión; separadores → `-` (plan §T5)."""
    assert paths.slugify_uri(uri) == slug


def test_slugify_uri_caps_the_length_without_trailing_dash() -> None:
    """Slugs de URI larguísimos quedan acotados y sin `-` final (nombres Observables)."""
    slug = paths.slugify_uri("https://example.org/" + "a" * 300 + ".pdf")
    assert len(slug) <= 80
    assert not slug.endswith("-")


def test_available_name_returns_the_slug_when_free() -> None:
    """Sin colisión el nombre es `<slug>.md`."""
    assert paths.available_name("ruiz-2024", lambda _name: False) == "ruiz-2024.md"


def test_available_name_appends_numeric_suffix_on_collision() -> None:
    """Colisión ⇒ primer sufijo numérico libre `<slug>-N.md` (N creciente)."""
    taken = {"ruiz-2024.md", "ruiz-2024-2.md"}
    assert paths.available_name("ruiz-2024", taken.__contains__) == "ruiz-2024-3.md"


def test_available_name_gives_up_after_the_cap() -> None:
    """Un directorio donde todo está tomado no es un bucle infinito: RuntimeError (⇒ INTERNAL)."""
    with pytest.raises(RuntimeError):
        paths.available_name("ruiz-2024", lambda _name: True)


# --- file: D16 — dentro del vault, nunca fuera --------------------------------------


def test_resolve_file_uri_accepts_paths_inside_the_vault(tmp_path: Path) -> None:
    """`file:` absoluto DENTRO del vault resuelve a la ruta pedida (D16, versión estricta)."""
    vault = tmp_path / "vault"
    inside = vault / "staging" / "nota.md"
    resolved = paths.resolve_file_uri(inside.as_uri(), vault)
    assert resolved == inside.resolve()


def test_resolve_file_uri_rejects_paths_outside_the_vault(tmp_path: Path) -> None:
    """D16: `file:` fuera del vault ⇒ ValueError → VALIDATION_ERROR (nunca se convierte)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ValueError):
        paths.resolve_file_uri(Path("/etc/hostname").as_uri(), vault)


def test_resolve_file_uri_rejects_traversal_out_of_the_vault(tmp_path: Path) -> None:
    """Un `..` en el `file:` no escapa: se resuelve y se rechaza (anti-traversal)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    traversal = vault.as_uri() + "/../secreto.md"
    with pytest.raises(ValueError):
        paths.resolve_file_uri(traversal, vault)


def test_resolve_file_uri_rejects_symlinks_pointing_outside(tmp_path: Path) -> None:
    """Un symlink DENTRO del vault que apunta FUERA también se rechaza (resolve estricto)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = tmp_path / "secreto.md"
    secret.write_text("secreto", encoding="utf-8")
    link = vault / "enlace.md"
    link.symlink_to(secret)
    with pytest.raises(ValueError):
        paths.resolve_file_uri(link.as_uri(), vault)


def test_resolve_file_uri_rejects_non_file_schemes(tmp_path: Path) -> None:
    """Solo `file:` pasa por esta helper; otros esquemas no se resuelven como ruta."""
    vault = tmp_path / "vault"
    with pytest.raises(ValueError):
        paths.resolve_file_uri("ftp://example.org/x.docx", vault)


@pytest.mark.parametrize(
    ("uri", "reason"),
    [
        ("file://otrohost/vault/nota.md", "host"),
        ("file:nota-relativa.md", "absoluta"),
    ],
)
def test_resolve_file_uri_rejects_remote_hosts_and_relative_paths(
    tmp_path: Path, uri: str, reason: str
) -> None:
    """`file://host/…` y `file:` relativo se rechazan: D16 solo acepta rutas locales absolutas.

    Un `file:` con host designa otro equipo y uno relativo depende del cwd del
    server: ambos escapan del vault por construcción, así que el borde los
    corta antes de que markitdown toque el disco.
    """
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(ValueError, match=reason):
        paths.resolve_file_uri(uri, vault)


def test_ensure_within_keeps_the_target_inside_base(tmp_path: Path) -> None:
    """Defensa en profundidad: destino dentro de base ⇒ pasa; fuera ⇒ ValueError."""
    base = tmp_path / "00-Resources"
    base.mkdir()
    assert (
        paths.ensure_within(base, base / "_inbox" / "x.md") == (base / "_inbox" / "x.md").resolve()
    )
    with pytest.raises(ValueError):
        paths.ensure_within(base, tmp_path / "fuera.md")


# --- esquemas aceptados por add_source (T5) ------------------------------------------


def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS falsa que resuelve todo a una dirección PÚBLICA — cero red en unit."""
    monkeypatch.setattr(
        paths.socket,
        "getaddrinfo",
        lambda *_: [(2, 0, 6, "", ("93.184.216.34", 0))],
    )


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.org/papers/ruiz-2024.pdf",
    ],
)
def test_validate_source_uri_accepts_http_and_https(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uri: str
) -> None:
    """`http(s)` con host PÚBLICO es admitido por el contrato de `add_source` (plan §T5).

    La DNS se stubbea a una IP pública: el caso rechazado por resolución
    interna está en los rejects de abajo (review SSRF 2026-10-27).
    """
    _public_dns(monkeypatch)
    paths.validate_source_uri(uri, tmp_path)  # no lanza


def test_validate_source_uri_accepts_file_inside_the_vault(tmp_path: Path) -> None:
    """`file:` DENTRO del vault pasa el borde (la ruta se resuelve, D16 solo expulsa fuera)."""
    inside = tmp_path / "staging" / "nota.md"
    paths.validate_source_uri(inside.as_uri(), tmp_path)  # no lanza


@pytest.mark.parametrize(
    "uri",
    [
        "ftp://example.org/x.docx",
        "mailto:autor@example.org",
        "https://",  # sin host: URI malformada para descarga
        "file:///etc/hostname",  # D16: fuera del vault (tmp_path ES el vault)
    ],
)
def test_validate_source_uri_rejects_everything_else(tmp_path: Path, uri: str) -> None:
    """Esquema desconocido, sin host o `file:` fuera ⇒ ValueError → VALIDATION_ERROR."""
    with pytest.raises(ValueError):
        paths.validate_source_uri(uri, tmp_path)


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost/articulo.html",  # loopback por nombre
        "http://mantequilla.local/articulo.html",  # mDNS (*.local), sin DNS real
        "http://127.0.0.1:8123/articulo.html",  # 127.0.0.0/8 (antes caso ACEPTADO)
        "http://[::1]:8123/articulo.html",  # ::1
        "http://0.0.0.0/articulo.html",  # unspecified
        "http://169.254.169.254/latest/meta-data/",  # link-local: cloud metadata
        "http://10.0.0.5/articulo.html",  # 10.0.0.0/8
        "http://172.16.0.1/articulo.html",  # 172.16.0.0/12
        "http://192.168.1.1/articulo.html",  # 192.168.0.0/16
        "http://usuario@example.org/articulo.html",  # userinfo en el URI
        "https://user:clave@89.234.183.98/articulo.html",  # userinfo (RFC 2732)
    ],
)
def test_validate_source_uri_rejects_ssrf_internal_hosts(uri: str) -> None:
    """Denylist SSRF: hosts internos/literal privado/userinfo ⇒ ValueError SIN fetch.

    Review Phase 2026-10-27: el fetch es anterior al rechazo por diseño del
    borde (el VALIDATION_ERROR sale ANTES de que el conversor vea nada) — los
    hosts de arriba son literales o `.local`/`localhost`, verificados SIN
    resolver DNS (y sin red: la unidad no toca el socket).
    """
    with pytest.raises(ValueError, match="red interna|userinfo"):
        paths.validate_source_uri(uri, Path("/vault"))


def test_validate_source_uri_rejects_hostname_resolving_to_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un hostname DNS que resuelve a IP PRIVADA también cae (SSRF por resolución)."""
    monkeypatch.setattr(
        paths.socket,
        "getaddrinfo",
        lambda *_: [(2, 0, 6, "", ("10.9.8.7", 0))],
    )

    with pytest.raises(ValueError, match="red interna"):
        paths.validate_source_uri("http://intranet.corp/articulo.html", Path("/vault"))
