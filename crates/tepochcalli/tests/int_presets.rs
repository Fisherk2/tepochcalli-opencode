//! T10 (F6a): embedded presets + badge table (D8.1/D8.2/D8.3).
//!
//! RED-first: this file must FAIL to compile before `src/config/` exists.

// Shared fakes: this target only needs one of them.
#[allow(dead_code)]
mod common;

use common::FakeHost;
use tepochcalli::config::{badge_for, parse_presets, parse_presets_str};
use tepochcalli::domain::Badge;
use tepochcalli::ports::{GpuInfo, HostProbe};

fn minilm(presets: &[tepochcalli::config::Preset]) -> &tepochcalli::config::Preset {
    lookup(
        presets,
        "paraphrase-multilingual-MiniLM-L12-v2",
        "default preset present",
    )
}

fn bgem3(presets: &[tepochcalli::config::Preset]) -> &tepochcalli::config::Preset {
    lookup(presets, "BAAI/bge-m3", "bge-m3 preset present")
}

fn lookup<'a>(
    presets: &'a [tepochcalli::config::Preset],
    hf_id: &str,
    msg: &str,
) -> &'a tepochcalli::config::Preset {
    presets
        .iter()
        .find(|p| p.hf_id == hf_id)
        .unwrap_or_else(|| panic!("{msg}: fixture must contain {hf_id}"))
}

#[test]
fn embedded_presets_match_spec_v2() {
    let presets = parse_presets().expect("embedded presets.toml parses");
    assert_eq!(presets.len(), 2, "exactly the 2 spec presets");

    let m = &presets[0];
    assert_eq!(m.name, "MiniLM multilingüe (default)");
    assert_eq!(m.hf_id, "paraphrase-multilingual-MiniLM-L12-v2");
    assert_eq!(m.dims, 384);
    assert_eq!(m.size_mb, 470);
    assert_eq!(m.disk_mb, 500);
    assert!((m.min_ram_gb - 0.7).abs() < f64::EPSILON);
    assert!((m.rec_ram_gb - 1.0).abs() < f64::EPSILON);
    assert!(!m.gpu_recommended);
    assert!(m.recommended_flag);

    let b = &presets[1];
    assert_eq!(b.name, "BGE-M3 (GPU)");
    assert_eq!(b.hf_id, "BAAI/bge-m3");
    assert_eq!(b.dims, 1024);
    assert_eq!(b.size_mb, 2300);
    assert_eq!(b.disk_mb, 2300);
    assert!((b.min_ram_gb - 2.4).abs() < f64::EPSILON);
    assert!((b.rec_ram_gb - 2.9).abs() < f64::EPSILON);
    assert!(b.gpu_recommended);
    assert!(!b.recommended_flag);

    // Exactly one preset is pre-selected (D7.2).
    assert_eq!(
        presets.iter().filter(|p| p.recommended_flag).count(),
        1,
        "exactly one recommended_flag"
    );
}

#[test]
fn malformed_toml_is_typed_error_not_silent_default() {
    let missing_dims = r#"
[[preset]]
name = "broken"
hf_id = "org/broken"
size_mb = 10
disk_mb = 10
min_ram_gb = 0.1
rec_ram_gb = 0.2
gpu_recommended = false
recommended_flag = false
"#;
    assert!(
        parse_presets_str(missing_dims).is_err(),
        "missing dims must fail"
    );

    let bad_type = r#"
[[preset]]
name = "broken"
hf_id = "org/broken"
dims = "not-a-number"
size_mb = 10
disk_mb = 10
min_ram_gb = 0.1
rec_ram_gb = 0.2
gpu_recommended = false
recommended_flag = false
"#;
    assert!(
        parse_presets_str(bad_type).is_err(),
        "bad dims type must fail"
    );
}

#[test]
fn badge_table_4gb_no_gpu() {
    let presets = parse_presets().expect("embedded presets parse");
    let host = FakeHost::new(Some(4.0), Some(4.0), Some(50.0), None);
    assert_eq!(
        badge_for(minilm(&presets), &host.snapshot()).0,
        Badge::Recommended
    );
    assert_eq!(
        badge_for(bgem3(&presets), &host.snapshot()).0,
        Badge::NotRecommended
    );
}

#[test]
fn badge_table_16gb_with_gpu() {
    let presets = parse_presets().expect("embedded presets parse");
    let host = FakeHost::new(
        Some(16.0),
        Some(16.0),
        Some(100.0),
        Some(GpuInfo {
            name: "nvidia".to_string(),
        }),
    );
    // Both fit with headroom: Recommended per ratio rule (accept Viable).
    for p in &presets {
        let (badge, _) = badge_for(p, &host.snapshot());
        assert!(
            badge == Badge::Recommended || badge == Badge::Viable,
            "{} on 16GB+GPU must be Recommended or Viable, got {badge:?}",
            p.hf_id
        );
    }
}

#[test]
fn gpu_required_without_gpu_is_not_recommended() {
    let presets = parse_presets().expect("embedded presets parse");
    // Even a huge-RAM host without GPU must flag the GPU preset.
    let host = FakeHost::new(Some(64.0), Some(64.0), Some(100.0), None);
    assert_eq!(
        badge_for(bgem3(&presets), &host.snapshot()).0,
        Badge::NotRecommended,
        "gpu_recommended && no GPU => NotRecommended"
    );
}

#[test]
fn not_recommended_preset_stays_selectable() {
    // D8.3: a warning badge never filters the row out of the lookup.
    let presets = parse_presets().expect("embedded presets parse");
    let host = FakeHost::new(Some(4.0), Some(4.0), Some(50.0), None);
    let (badge, _) = badge_for(bgem3(&presets), &host.snapshot());
    assert_eq!(badge, Badge::NotRecommended);
    assert!(
        bgem3(&presets).hf_id == "BAAI/bge-m3",
        "NotRecommended preset must still be returned by lookup"
    );
}

#[test]
fn probe_failure_yields_unknown_badge_and_declared_facts() {
    let presets = parse_presets().expect("embedded presets parse");
    let host = FakeHost::new(None, None, None, None);
    assert!(host.ram_available_gb().is_none());
    for p in &presets {
        let (badge, facts) = badge_for(p, &host.snapshot());
        assert_eq!(badge, Badge::Unknown, "{} must be Unknown", p.hf_id);
        assert_eq!(facts.disk_mb, p.disk_mb);
        // ResourceFacts.gpu retirado (espejo muerto de preset.gpu_recommended;
        // la fila del menú ya lee el preset directamente).
        assert!(facts.ram_mb > 0, "declared RAM facts still returned");
    }
}

#[test]
fn available_ram_falls_back_to_total() {
    let presets = parse_presets().expect("embedded presets parse");
    // Probe reports total but not available: menu still badges off total.
    let host = FakeHost::new(Some(4.0), None, Some(50.0), None);
    assert_eq!(
        badge_for(minilm(&presets), &host.snapshot()).0,
        Badge::Recommended
    );
}

/// L5-1: el snapshot del menú se captura UNA vez — tres badge_for sobre los
/// mismos facts NO re-probean (FakeHost cuenta los snapshots servidos).
#[test]
fn menu_snapshots_once_not_per_row() {
    let presets = parse_presets().expect("embedded presets parse");
    let host = FakeHost::new(Some(16.0), Some(16.0), Some(100.0), None);
    let facts = host.snapshot();
    assert_eq!(host.snapshot_count(), 1, "un snapshot al capturar");

    for _ in 0..3 {
        let _ = badge_for(minilm(&presets), &facts);
    }
    assert_eq!(
        host.snapshot_count(),
        1,
        "tres badge_for sobre el snapshot no re-probean RAM/GPU"
    );
}
