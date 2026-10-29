//! Text-shape helpers for the wizard's artifacts (TD-18): the `key = "value"`
//! config reader with its TOML escape, and the minimal JSON readers for the
//! one-line flow CLI contracts (`embed-check`, `refresh`, `rag_status`).
//!
//! One copy each — shared by the F6 menu, the swap, maintenance, F7 and F8
//! (antes: cinco copias idénticas del mismo lector). Hand-rolled on purpose:
//! the contracts are flat one-line JSON — smaller than invoking a serde
//! dependency in the spawn path — and every reader/escaper here is covered
//! by the round-trip tests below (`reader ↔ writer`, pinned in dd12cef).

/// Minimal `key = "value"` reader for the wizard-written config (same shape
/// as the F6 writer — never hand-edited TOML). Undoes [`toml_escape`]'s
/// escaping (`\"` first, then `\\`) so a model id reads back byte-identical,
/// and returns `Some("")` for an empty value (the consumer decides whether
/// blank means "absent"; see [`super::failure`] for the filtering example).
///
/// Nota: `strip_prefix` casa por prefijo (un `mode` entra en las líneas
/// `model…`); hoy el cheque de `=` las rechaza, así que la herencia del
/// matching es inofensiva — una clave futura con prefijo de otra requeriría
/// el límite de palabra explícito.
pub(crate) fn config_value(body: &str, key: &str) -> Option<String> {
    body.lines().find_map(|line| {
        let rest = line
            .trim()
            .strip_prefix(key)?
            .trim_start()
            .strip_prefix('=')?;
        let value = rest.trim().strip_prefix('"')?.strip_suffix('"')?;
        Some(value.replace("\\\"", "\"").replace("\\\\", "\\"))
    })
}

/// TOML writer-side escape: backslash first, then the quote. Pinned pair
/// reader↔writer: [`config_value`] undoes exactly this order (dd12cef).
pub(crate) fn toml_escape(raw: &str) -> String {
    raw.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Minimal JSON reader for the one-line flow contracts (same hand-rolled
/// shape as the F6 gate and F7 refresh parsers: flat top-level keys).
///
/// Quote discipline: inside a quoted value the whitespace is part of the
/// data (no trim); bare values are trimmed unquoted-style.
pub(crate) fn json_raw<'a>(body: &'a str, key: &str) -> Option<&'a str> {
    let needle = format!("\"{key}\"");
    let after_key = body.find(&needle).map(|i| &body[i + needle.len()..])?;
    let value = after_key.trim_start().strip_prefix(':')?.trim_start();
    if let Some(quoted) = value.strip_prefix('"') {
        let mut end = None;
        let mut escaped = false;
        for (i, c) in quoted.char_indices() {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                end = Some(i);
                break;
            }
        }
        return end.map(|i| &quoted[..i]);
    }
    Some(value.split([',', '}']).next().unwrap_or_default().trim())
}

pub(crate) fn json_bool(body: &str, key: &str) -> Option<bool> {
    match json_raw(body, key)? {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    }
}

pub(crate) fn json_u64(body: &str, key: &str) -> Option<u64> {
    json_raw(body, key)?.parse().ok()
}

pub(crate) fn json_u32(body: &str, key: &str) -> Option<u32> {
    json_raw(body, key)?.parse().ok()
}

/// Unescapes [`json_escape`]'s output (`\"` first, then `\\`), same order as
/// [`config_value`] — so a model id written by the wizard reads back intact.
pub(crate) fn json_string(body: &str, key: &str) -> Option<String> {
    json_raw(body, key).map(|raw| raw.replace("\\\"", "\"").replace("\\\\", "\\"))
}

/// JSON writer-side escape (models written into sidecars/report bodies).
pub(crate) fn json_escape(raw: &str) -> String {
    raw.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Display of an optional measured figure: present ⇒ value, absent ⇒ the
/// shared "(sin dato)" placeholder (swap, reindex and the two CLI flags).
///
/// `pub` (not `pub(crate)`) because `main.rs` draws the same two summary
/// lines; the rest of the module stays internal.
pub fn or_fallback<T: ToString>(value: Option<T>) -> String {
    value
        .map(|v| v.to_string())
        .unwrap_or_else(|| "(sin dato)".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Id hostil pero plausible: comilla y barra dentro del valor.
    const RAW: &str = "modelo \"con comillas\" y \\ barra";

    /// Cuerpo TOML mínimo con la misma forma que escriben a la vez las tres
    /// escritoras reales (F6, swap, maintenance) — solo el escape importa
    /// aquí.
    fn toml_body(model: &str) -> String {
        format!(
            "[embedding]\nprovider = \"local\"\nmodel = \"{}\"\n",
            toml_escape(model)
        )
    }

    // ---- TOML reader/escaper: escape de ida, des-escapado de vuelta --------

    #[test]
    fn toml_escape_escapes_backslash_and_quote() {
        assert_eq!(toml_escape("a\\b"), "a\\\\b");
        assert_eq!(toml_escape("a\"b"), "a\\\"b");
        assert_eq!(toml_escape(RAW), "modelo \\\"con comillas\\\" y \\\\ barra");
    }

    #[test]
    fn config_value_unescapes_what_toml_escape_writes() {
        let body = toml_body(RAW);
        assert_eq!(
            config_value(&body, "model").as_deref(),
            Some(RAW),
            "leer la config debe devolver el id original, got:\n{body}"
        );
        // Vuelta: re-escapar lo leído reproduce el mismo cuerpo.
        let read = config_value(&body, "model").unwrap_or_default();
        assert_eq!(toml_body(&read), body);
    }

    #[test]
    fn every_escaped_value_round_trips_through_config() {
        // Exhaustivo sobre el alfabeto que el escape toca (longitud ≤ 3).
        let alphabet = ['a', '"', '\\'];
        for a in alphabet {
            for b in alphabet {
                for c in alphabet {
                    let raw: String = [a, b, c].iter().collect();
                    let body = toml_body(&raw);
                    assert_eq!(
                        config_value(&body, "model").as_deref(),
                        Some(raw.as_str()),
                        "round-trip roto para {raw:?} en:\n{body}"
                    );
                }
            }
        }
    }

    #[test]
    fn config_value_reads_plain_values_and_ignores_other_keys() {
        let body = toml_body("BAAI/bge-m3");
        assert_eq!(config_value(&body, "model").as_deref(), Some("BAAI/bge-m3"));
        assert_eq!(config_value(&body, "provider").as_deref(), Some("local"));
        assert_eq!(config_value(&body, "api_key"), None);
        assert_eq!(config_value(&body, "mode"), None);

        // Un valor vacío es `Some("")`: el consumidor decide si es ausencia.
        assert_eq!(config_value("model = \"\"\n", "model").as_deref(), Some(""));
    }

    // ---- JSON readers ----------------------------------------------------

    #[test]
    fn json_raw_reads_quoted_and_bare_values() {
        let body = "{\"model\":\"a\\\"b\",\"n\":42,\"flag\":true}";
        assert_eq!(json_raw(body, "model"), Some("a\\\"b"));
        assert_eq!(json_raw(body, "n"), Some("42"));
        assert_eq!(json_raw(body, "flag"), Some("true"));
        assert_eq!(json_raw(body, "missing"), None);
        // Un valor literal `null` es texto, no ausencia.
        assert_eq!(
            json_string("{\"model\":null}", "model").as_deref(),
            Some("null")
        );
    }

    #[test]
    fn json_raw_keeps_whitespace_inside_quotes() {
        let body = "{\"model\":\"  padded  \",\"n\": 7 }";
        assert_eq!(json_raw(body, "model"), Some("  padded  "));
        assert_eq!(json_string(body, "model").as_deref(), Some("  padded  "));
        assert_eq!(json_u64(body, "n"), Some(7));
    }

    #[test]
    fn json_scalars_parse_typed_and_reject_garbage() {
        let body = "{\"ok\":true,\"no\":false,\"n\":42,\"big\":5000000000}";
        assert_eq!(json_bool(body, "ok"), Some(true));
        assert_eq!(json_bool(body, "no"), Some(false));
        assert_eq!(json_bool(body, "n"), None, "un número no es un bool");
        assert_eq!(json_bool(body, "missing"), None);
        assert_eq!(json_u64(body, "n"), Some(42));
        assert_eq!(json_u32(body, "n"), Some(42));
        assert_eq!(json_u32(body, "big"), None, "desbordar u32 no es 0");
        assert_eq!(json_u64(body, "missing"), None);
    }

    #[test]
    fn json_escape_round_trips_through_json_string() {
        let body = format!("{{\"model\":\"{}\"}}", json_escape(RAW));
        assert_eq!(json_string(&body, "model").as_deref(), Some(RAW));
    }

    #[test]
    fn or_fallback_names_absent_figures_and_passes_present_ones() {
        assert_eq!(or_fallback(Some(384u32)), "384");
        assert_eq!(or_fallback::<u32>(None), "(sin dato)");
    }
}
