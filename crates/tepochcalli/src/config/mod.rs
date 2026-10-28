//! Wizard configuration data: embedded catalogues, no I/O.

pub mod presets;

pub use presets::{
    badge_for, parse_presets, parse_presets_str, preset_by_hf_id, Preset, PresetError,
};
