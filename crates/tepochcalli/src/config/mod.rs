//! Wizard configuration data: embedded catalogues, no I/O.

pub mod presets;

pub use presets::{
    badge_for, default_and_large, parse_presets, parse_presets_str, Preset, PresetError,
};
