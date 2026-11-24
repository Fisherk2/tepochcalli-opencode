//! R-offline-1 (T13): qué endpoint debe alcanzar `install`/`update` antes de
//! su primer write. Decisión pura: el sondeo lo hace el adapter `HttpClient`.

/// Endpoint del preflight de red de `install`/`update`. `None` = payload
/// local: F3 no toca la red en esa rama (las descargas posteriores las
/// compensa su propia fase).
#[must_use]
pub fn payload_endpoint(
    payload_dir: Option<&str>,
    payload_url: Option<&str>,
    release_asset_url: &str,
) -> Option<String> {
    match (payload_dir, payload_url) {
        // Conflicto ya rechazado como uso (`validate_payload_flags`): sin sonda.
        (Some(_), Some(_)) => None,
        (_, Some(url)) => Some(url.to_string()),
        (Some(_), None) => None,
        (None, None) => Some(release_asset_url.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::payload_endpoint;

    const RELEASE: &str = "https://mirror.test/x.tar.gz";

    #[test]
    fn override_url_wins() {
        assert_eq!(
            payload_endpoint(None, Some("https://override.test/p.tar.gz"), RELEASE),
            Some("https://override.test/p.tar.gz".to_string())
        );
    }

    #[test]
    fn local_payload_needs_no_network() {
        assert_eq!(payload_endpoint(Some("/tmp/payload"), None, RELEASE), None);
    }

    #[test]
    fn release_path_probes_the_release_asset() {
        assert_eq!(
            payload_endpoint(None, None, RELEASE),
            Some(RELEASE.to_string())
        );
    }

    /// `validate_payload_flags` ya lo rechaza como uso; defensivo ⇒ sin sonda.
    #[test]
    fn conflicting_flags_probe_nothing() {
        assert_eq!(
            payload_endpoint(
                Some("/tmp/payload"),
                Some("https://override.test/p"),
                RELEASE
            ),
            None
        );
    }
}
