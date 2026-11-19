//! Domain unit tests (T3): phase ordering, exit-code ranges and `E_*` mapping (§5.4).

use tepochcalli::application::EMBEDDER_PATHS;
use tepochcalli::domain::version::compare;
use tepochcalli::domain::{
    installed_state, menu_spec, Badge, EmbedderChoice, InstalledState, MenuAction, Phase, Version,
    WizardError,
};

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

// ---- H5 menu matrix (spec-installer-wizard.md §TUI full-screen) ----------

/// Botón a botón, con las razones literales de la spec.
#[test]
fn h5_menu_matrix_matches_the_spec() {
    type Expected = [(MenuAction, bool, Option<&'static str>); 5];

    use InstalledState::{Ahead, NotInstalled, Outdated, UpToDate};
    use MenuAction::{ChangeEmbedder, Desinstall, Exit, Install, Update};

    const NO_INSTALL: &str = "no hay instalación aún";
    const UP_TO_DATE: &str = "versión al día";
    const ALREADY_INSTALLED: &str = "ya existe instalación";
    const AHEAD: &str = "versión instalada mayor que la del wizard";

    let cases: [(InstalledState, Expected); 4] = [
        (
            NotInstalled,
            [
                (Update, false, Some(NO_INSTALL)),
                (ChangeEmbedder, false, Some(NO_INSTALL)),
                (Desinstall, false, Some(NO_INSTALL)),
                (Install, true, None),
                (Exit, true, None),
            ],
        ),
        (
            UpToDate,
            [
                (Update, false, Some(UP_TO_DATE)),
                (ChangeEmbedder, true, None),
                (Desinstall, true, None),
                (Install, false, Some(UP_TO_DATE)),
                (Exit, true, None),
            ],
        ),
        (
            Outdated,
            [
                (Update, true, None),
                (ChangeEmbedder, true, None),
                (Desinstall, true, None),
                (Install, false, Some(ALREADY_INSTALLED)),
                (Exit, true, None),
            ],
        ),
        (
            Ahead,
            [
                (Update, false, Some(AHEAD)),
                (ChangeEmbedder, false, Some(AHEAD)),
                (Desinstall, false, Some(AHEAD)),
                (Install, false, Some(AHEAD)),
                (Exit, true, None),
            ],
        ),
    ];

    for (state, expected) in cases {
        let spec = menu_spec(state);
        assert_eq!(spec.buttons.len(), 5, "{state:?}");
        for (button, (action, enabled, reason)) in spec.buttons.iter().zip(expected) {
            assert_eq!(button.action, action, "{state:?}");
            assert_eq!(button.enabled, enabled, "{state:?} {action:?}");
            assert_eq!(button.reason, reason, "{state:?} {action:?}");
        }
    }
}

#[test]
fn exit_is_never_disabled_and_ahead_only_offers_exit() {
    for state in [
        InstalledState::NotInstalled,
        InstalledState::UpToDate,
        InstalledState::Outdated,
        InstalledState::Ahead,
    ] {
        let exit = menu_spec(state)
            .buttons
            .into_iter()
            .find(|b| b.action == MenuAction::Exit);
        assert!(
            exit.is_some_and(|b| b.enabled),
            "{state:?} must keep Exit enabled (H10)"
        );
    }

    let enabled: Vec<MenuAction> = menu_spec(InstalledState::Ahead)
        .buttons
        .into_iter()
        .filter(|b| b.enabled)
        .map(|b| b.action)
        .collect();
    assert_eq!(enabled, [MenuAction::Exit]);
}

#[test]
fn ahead_state_shows_the_exact_uvx_refresh_command() {
    let notice = menu_spec(InstalledState::Ahead).notice.unwrap_or_default();
    assert!(
        notice.contains("uvx --refresh tepochcalli"),
        "Ahead notice lacks the copyable command: {notice:?}"
    );
    // Los demás estados no piden refrescar la caché.
    for state in [
        InstalledState::NotInstalled,
        InstalledState::UpToDate,
        InstalledState::Outdated,
    ] {
        let notice = menu_spec(state).notice.unwrap_or_default();
        assert!(!notice.contains("uvx --refresh"), "{state:?}");
    }
}

#[test]
fn installed_state_derives_from_the_two_versions() {
    use InstalledState::{Ahead, NotInstalled, Outdated, UpToDate};

    assert_eq!(installed_state(None, "0.1.0"), NotInstalled);
    assert_eq!(installed_state(Some("0.1.0"), "0.1.0"), UpToDate);
    assert_eq!(installed_state(Some("0.1.0-beta.1"), "0.1.0"), Outdated);
    assert_eq!(installed_state(Some("0.2.0"), "0.1.0"), Ahead);
    // Fichero ilegible: conservador, nunca Install sobre un runtime existente.
    assert_eq!(installed_state(Some("garbage"), "0.1.0"), UpToDate);
    assert_eq!(installed_state(Some("0.1.0"), "garbage"), UpToDate);
}

// ---- Semver propio (sin dependencia nueva) ------------------------------

#[test]
fn semver_orders_the_installed_against_the_wizard() {
    use std::cmp::Ordering::{Equal, Greater, Less};

    assert_eq!(compare("0.1.0-beta.1", "0.1.0"), Some(Less));
    assert_eq!(compare("0.1.0", "0.1.0"), Some(Equal));
    assert_eq!(compare("0.1.0", "0.2.0"), Some(Less));
    assert_eq!(compare("0.2.0", "0.1.0"), Some(Greater));

    // Precedencia §11: alfa < alfa.1 < alfa.beta < beta < beta.2 < rc.1 < release.
    let chain = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    ];
    for pair in chain.windows(2) {
        assert_eq!(compare(pair[0], pair[1]), Some(Less), "{pair:?}");
        assert_eq!(compare(pair[1], pair[0]), Some(Greater), "{pair:?}");
    }

    // Numérico < alfanumérico cuando ambos existen.
    assert_eq!(compare("1.0.0-2", "1.0.0-alpha"), Some(Less));
}

#[test]
fn semver_rejects_garbage_instead_of_defaulting() {
    for bad in [
        "",
        "1",
        "1.2",
        "1.2.3.4",
        "v1.2.3",
        "1.2.x",
        "1.2.3-",
        "1.2.3-beta..1",
        "1.2.3+build",
        " 1.2.3",
    ] {
        assert!(Version::parse(bad).is_none(), "{bad:?} must not parse");
        assert_eq!(compare(bad, "0.1.0"), None, "{bad:?}");
    }
}
