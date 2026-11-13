//! Filas del menú D7.1 y entradas de teclado del F6.
//!
//! El orden de filas es [`super::embedder_menu::EMBEDDER_PATHS`]; aquí solo se
//! formatea cada fila con su badge/figura declarada y se re-pregunta hasta que
//! el valor no está en blanco (un script agotado es `UserAborted`, nunca una
//! suposición).

use crate::config::{badge_for, Preset};
use crate::domain::{Badge, WizardError};
use crate::ports::Ui;

use super::embedder_menu::Provenance;

pub(super) fn badge_label(badge: Badge) -> &'static str {
    match badge {
        Badge::Recommended => "recomendado",
        Badge::Viable => "viable",
        Badge::NotRecommended => "no recomendado",
        Badge::Unknown => "sin datos",
    }
}

pub(super) fn preset_option(preset: &Preset, facts: &crate::ports::HostFacts) -> String {
    let (badge, resource) = badge_for(preset, facts);
    let gpu = if preset.gpu_recommended {
        "requerida"
    } else {
        "no requerida"
    };
    let provenance = Provenance::Declared.label();
    format!(
        "{} [{}] 💾 {}MB ({provenance}) · 🧠 {}MB ({provenance}) · 🎮 {gpu}",
        preset.name,
        badge_label(badge),
        resource.disk_mb,
        resource.ram_mb
    )
}

/// The 5 rows in [`super::embedder_menu::EMBEDDER_PATHS`] order; preset rows
/// carry badges + declared figures, the free-id row is static (its estimate
/// arrives after the user types the id). L5-1: los facts del snapshot (uno por
/// corrida) alimentan ambas filas — sin re-probe por fila.
pub(super) fn build_options(
    default: &Preset,
    large: &Preset,
    facts: &crate::ports::HostFacts,
) -> Vec<String> {
    vec![
        preset_option(default, facts),
        preset_option(large, facts),
        "ID libre de HuggingFace — estima vía API + gate test-embed".to_string(),
        "API externa vía LiteLLM (clave solo en config gitignored)".to_string(),
        "Configurar después (sin índice, RAG degraded)".to_string(),
    ]
}

/// Re-ask until the answer is non-blank; an exhausted script surfaces
/// `UserAborted` (never a guess).
pub(super) fn ask_non_empty(ui: &dyn Ui, prompt: &str) -> Result<String, WizardError> {
    loop {
        let raw = ui.input(prompt, None)?;
        let value = raw.trim().to_string();
        if !value.is_empty() {
            return Ok(value);
        }
        ui.panel(
            "Falta un dato",
            "El valor no puede estar vacío; pulsa Ctrl-C para volver al menú.",
        );
    }
}

/// `ask_non_empty` sin eco: clave/token via `input_secret` (L2-7). La clave
/// no puede volver a cero en un terminal (headless o real).
pub(super) fn ask_secret_non_empty(ui: &dyn Ui, prompt: &str) -> Result<String, WizardError> {
    loop {
        let raw = ui.input_secret(prompt)?;
        let value = raw.trim().to_string();
        if !value.is_empty() {
            return Ok(value);
        }
        ui.panel(
            "Falta un dato",
            "El valor no puede estar vacío; pulsa Ctrl-C para volver al menú.",
        );
    }
}

#[cfg(test)]
mod tests {
    use super::badge_label;
    use crate::domain::Badge;

    #[test]
    fn badge_label_covers_every_variant() {
        assert_eq!(badge_label(Badge::Recommended), "recomendado");
        assert_eq!(badge_label(Badge::Viable), "viable");
        assert_eq!(badge_label(Badge::NotRecommended), "no recomendado");
        assert_eq!(badge_label(Badge::Unknown), "sin datos");
    }
}
