//! Preset catalogue (D7.2) + hardware badges (D8.1/D8.2/D8.3).
//!
//! Data layer only: no UI, no network. `presets.toml` rides in the binary
//! via `include_str!`; badges are pure functions over [`HostProbe`].

use crate::domain::{Badge, ResourceFacts};

/// One row of the embedder menu (spec-embeddings.md §presets.toml v2).
#[derive(Debug, Clone, PartialEq)]
pub struct Preset {
    /// Menu label.
    pub name: String,
    /// HuggingFace id.
    pub hf_id: String,
    /// Embedding dimensions.
    pub dims: u32,
    /// Download weight in MB (HF blob).
    pub size_mb: u64,
    /// Disk footprint in MB after download (D8.1).
    pub disk_mb: u64,
    /// Minimum RAM in GiB to run on CPU (D8.1).
    pub min_ram_gb: f64,
    /// Comfortable RAM in GiB — badge ratio denominator (D8.2).
    pub rec_ram_gb: f64,
    /// Show GPU warning when the host has none (never blocks, D8.3).
    pub gpu_recommended: bool,
    /// Exactly one preset carries the RECOMENDADO pre-select (D7.2).
    pub recommended_flag: bool,
}

/// Typed parse failures — a malformed preset never degrades silently.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum PresetError {
    /// A required `key` is absent from a `[[preset]]` block.
    #[error("preset is missing field `{0}`")]
    MissingField(&'static str),
    /// A `key` is present but its value does not parse.
    #[error("preset field `{field}` has invalid value `{value}`")]
    InvalidValue {
        /// Offending key.
        field: &'static str,
        /// Raw value text.
        value: String,
    },
    /// No `[[preset]]` block found at all.
    #[error("no [[preset]] entries found")]
    NoPresets,
}

/// Parse the embedded catalogue.
pub fn parse_presets() -> Result<Vec<Preset>, PresetError> {
    parse_presets_str(include_str!("presets.toml"))
}

/// Parse catalogue text (same rules as the embedded file).
pub fn parse_presets_str(text: &str) -> Result<Vec<Preset>, PresetError> {
    let mut presets = Vec::new();
    let mut current: Vec<(&str, &str)> = Vec::new();
    let mut seen_block = false;

    for raw_line in text.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if line == "[[preset]]" {
            if seen_block {
                presets.push(finish_block(&current)?);
                current = Vec::new();
            }
            seen_block = true;
            continue;
        }
        if !seen_block {
            continue;
        }
        let (key, value) = line
            .split_once('=')
            .map(|(k, v)| (k.trim(), strip_inline_comment(v.trim()).trim()))
            .ok_or_else(|| PresetError::InvalidValue {
                field: "line",
                value: raw_line.to_string(),
            })?;
        current.push((key, value));
    }
    if seen_block {
        presets.push(finish_block(&current)?);
    }
    if presets.is_empty() {
        return Err(PresetError::NoPresets);
    }
    Ok(presets)
}

// Strip a trailing `# comment` that is outside a quoted string.
fn strip_inline_comment(value: &str) -> &str {
    let mut in_quotes = false;
    for (i, c) in value.char_indices() {
        if c == '"' {
            in_quotes = !in_quotes;
        } else if c == '#' && !in_quotes {
            return value[..i].trim_end();
        }
    }
    value
}

fn finish_block(fields: &[(&str, &str)]) -> Result<Preset, PresetError> {
    let get = |key: &'static str| {
        fields
            .iter()
            .find(|(k, _)| *k == key)
            .map(|(_, v)| *v)
            .ok_or(PresetError::MissingField(key))
    };
    let parse_num = |key: &'static str, raw: &str| {
        raw.parse::<f64>().map_err(|_| PresetError::InvalidValue {
            field: key,
            value: raw.to_string(),
        })
    };
    let parse_bool = |key: &'static str, raw: &str| match raw {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(PresetError::InvalidValue {
            field: key,
            value: raw.to_string(),
        }),
    };

    let dims_f = parse_num("dims", get("dims")?)?;
    let size_f = parse_num("size_mb", get("size_mb")?)?;
    let disk_f = parse_num("disk_mb", get("disk_mb")?)?;
    let (dims, size_mb, disk_mb) = (
        u32::try_from(to_int("dims", dims_f)?).map_err(|_| PresetError::InvalidValue {
            field: "dims",
            value: dims_f.to_string(),
        })?,
        to_int("size_mb", size_f)?,
        to_int("disk_mb", disk_f)?,
    );
    Ok(Preset {
        name: unquote_value("name", get("name")?)?.to_string(),
        hf_id: unquote_value("hf_id", get("hf_id")?)?.to_string(),
        dims,
        size_mb,
        disk_mb,
        min_ram_gb: parse_num("min_ram_gb", get("min_ram_gb")?)?,
        rec_ram_gb: parse_num("rec_ram_gb", get("rec_ram_gb")?)?,
        gpu_recommended: parse_bool("gpu_recommended", get("gpu_recommended")?)?,
        recommended_flag: parse_bool("recommended_flag", get("recommended_flag")?)?,
    })
}

fn unquote_value<'a>(key: &'static str, raw: &'a str) -> Result<&'a str, PresetError> {
    raw.strip_prefix('"')
        .and_then(|s| s.strip_suffix('"'))
        .ok_or_else(|| PresetError::InvalidValue {
            field: key,
            value: raw.to_string(),
        })
}

// Integers must be whole and non-negative; floats stay floats.
fn to_int(field: &'static str, value: f64) -> Result<u64, PresetError> {
    if value < 0.0 || value.fract() != 0.0 {
        return Err(PresetError::InvalidValue {
            field,
            value: value.to_string(),
        });
    }
    Ok(value as u64)
}

/// Badge + declared facts for one preset over the run's `HostFacts` snapshot
/// (D8.2 + L5-1: el snapshot se captura una vez por menú; aquí solo lee).
///
/// Available RAM first, total as fallback; all-`None` probe → `Unknown`
/// with declared numbers (never a crash). A `gpu_recommended` preset on a
/// GPU-less host is `NotRecommended` but stays selectable (D8.3).
#[must_use]
pub fn badge_for(preset: &Preset, facts: &crate::ports::HostFacts) -> (Badge, ResourceFacts) {
    let resource = ResourceFacts {
        disk_mb: preset.disk_mb,
        ram_mb: (preset.rec_ram_gb * 1024.0) as u64,
    };
    let Some(avail) = facts.ram_available_gb.or(facts.ram_total_gb) else {
        return (Badge::Unknown, resource);
    };
    if preset.gpu_recommended && facts.gpu.is_none() {
        return (Badge::NotRecommended, resource);
    }
    let badge = if avail >= preset.rec_ram_gb * 1.5 {
        Badge::Recommended
    } else if avail >= preset.rec_ram_gb {
        Badge::Viable
    } else {
        Badge::NotRecommended
    };
    (badge, resource)
}

/// La fila recomendada (default) y la de mayor tamaño (large), en orden de
/// menú D7.1. Única fuente compartida por el menú F6 y el swap: ambos
/// buscaban `recommended_flag` a mano con dos iteradores idénticos.
///
/// `None` cuando el catálogo no trae exactamente el par (error parseado no
/// llega aquí: un catálogo válido siempre tiene ambas mitades, D7.2).
#[must_use]
pub fn default_and_large(presets: &[Preset]) -> Option<(&Preset, &Preset)> {
    let default = presets.iter().find(|preset| preset.recommended_flag)?;
    let large = presets.iter().find(|preset| !preset.recommended_flag)?;
    Some((default, large))
}
