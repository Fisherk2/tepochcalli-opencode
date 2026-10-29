//! Domain unit tests (T3): phase ordering, exit-code ranges and `E_*` mapping (§5.4).

use tepochcalli::application::EMBEDDER_PATHS;
use tepochcalli::domain::{Badge, EmbedderChoice, Phase, WizardError};

#[test]
fn phase_ordering_f1_before_f8() {
    assert!(Phase::F1.order_index() < Phase::F8.order_index());
    // Full chain is strictly increasing.
    let all = Phase::all();
    assert_eq!(all.len(), 8);
    let mut prev = all[0].order_index();
    for phase in &all[1..] {
        assert!(phase.order_index() > prev);
        prev = phase.order_index();
    }
}

#[test]
fn phase_names_cover_f1_to_f8() {
    let names: Vec<&str> = Phase::all().iter().copied().map(Phase::name).collect();
    assert_eq!(names, ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8",]);
}

#[test]
fn exit_codes_land_in_spec_ranges() {
    // (variant, expected range) per tasks/plan.md §5.4.
    let cases: &[(WizardError, std::ops::RangeInclusive<u8>)] = &[
        (WizardError::PrereqRam, 10..=19),
        (WizardError::PrereqDisk, 10..=19),
        (WizardError::PrereqPlatform, 10..=19),
        (WizardError::NetDownload, 20..=29),
        (WizardError::OfflineNoCache, 20..=29),
        (WizardError::ApiAuth, 20..=29),
        (WizardError::DiskFull, 30..=39),
        (WizardError::PermissionDenied, 30..=39),
        (WizardError::PayloadCorrupt, 30..=39),
        (WizardError::ModelInvalid, 40..=u8::MAX),
        (WizardError::ModelMismatch, 40..=u8::MAX),
        (WizardError::PhaseFailed, 40..=u8::MAX),
        (WizardError::Internal, 40..=u8::MAX),
        (WizardError::UserAborted, 40..=u8::MAX),
    ];
    for (err, range) in cases {
        assert!(
            range.contains(&err.exit_code()),
            "{err:?} exit {} outside {range:?}",
            err.exit_code()
        );
    }
}

#[test]
fn exact_exit_numbers_match_plan_5_4() {
    // §5.4 pins two numbers; the rest are the wizard's documented choice.
    assert_eq!(WizardError::OfflineNoCache.exit_code(), 21);
    assert_eq!(WizardError::ApiAuth.exit_code(), 22);
}

#[test]
fn e_star_mapping_table() {
    assert_eq!(
        WizardError::OfflineNoCache.e_star(),
        Some("E_OFFLINE_NO_CACHE")
    );
    assert_eq!(WizardError::ApiAuth.e_star(), Some("E_API_AUTH"));
    assert_eq!(WizardError::ModelInvalid.e_star(), Some("E_MODEL_INVALID"));
    assert_eq!(
        WizardError::ModelMismatch.e_star(),
        Some("E_MODEL_MISMATCH")
    );
    // No MCP equivalent: no E_* code.
    for err in [
        WizardError::PrereqRam,
        WizardError::PrereqDisk,
        WizardError::PrereqPlatform,
        WizardError::NetDownload,
        WizardError::DiskFull,
        WizardError::PermissionDenied,
        WizardError::PayloadCorrupt,
        WizardError::PhaseFailed,
        WizardError::Internal,
        WizardError::UserAborted,
    ] {
        assert_eq!(err.e_star(), None, "{err:?} must map to no E_*");
    }
}

#[test]
fn embedder_menu_has_five_paths_with_default() {
    // Tras retirar EmbedderChoice::all()/default_path(), EMBEDDER_PATHS es la
    // única fuente del orden D7.1 decidido.
    assert_eq!(EMBEDDER_PATHS.len(), 5, "D7.1 fixes exactly 5 menu paths");
    assert_eq!(
        EMBEDDER_PATHS.first(),
        Some(&EmbedderChoice::PresetDefault),
        "default preselected = paraphrase-multilingual-MiniLM-L12-v2"
    );
}

#[test]
fn badge_variants_exist() {
    let _ = Badge::Recommended;
    let _ = Badge::Viable;
    let _ = Badge::NotRecommended;
    let _ = Badge::Unknown;
}
