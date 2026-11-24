//! Semver comparator for the H5 menu (pure): installed vs wizard version.
//!
//! Hand-rolled on purpose: T7 forbids a new dependency for a need this
//! small (ADR-011 ledger). Accepted grammar is exactly what the wizard
//! writes and reads back — `major.minor.patch[-prerelease]` — with semver
//! §11 precedence. Build metadata (`+…`) does not change precedence, so it
//! is rejected as garbage instead of being silently stripped: an unparsable
//! version falls back to the conservative menu state (see `menu`).

use std::cmp::Ordering;
use std::fmt;

/// Parsed `major.minor.patch[-prerelease]` version.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Version {
    major: u64,
    minor: u64,
    patch: u64,
    pre: Option<String>,
}

impl Version {
    /// `None` for anything that is not `digits.digits.digits[-pre]`: no
    /// defaults are invented for a malformed version.
    #[must_use]
    pub fn parse(raw: &str) -> Option<Version> {
        let (core, pre) = match raw.split_once('-') {
            Some((_, "")) => return None,
            Some((core, pre)) => (core, Some(pre)),
            None => (raw, None),
        };

        let mut numbers = core.split('.');
        let major = parse_number(numbers.next()?)?;
        let minor = parse_number(numbers.next()?)?;
        let patch = parse_number(numbers.next()?)?;
        if numbers.next().is_some() {
            return None;
        }

        if let Some(pre) = pre {
            let valid = pre.split('.').all(|id| {
                !id.is_empty() && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
            });
            if !valid {
                return None;
            }
        }

        Some(Version {
            major,
            minor,
            patch,
            pre: pre.map(str::to_string),
        })
    }
}

impl fmt::Display for Version {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}.{}", self.major, self.minor, self.patch)?;
        if let Some(pre) = &self.pre {
            write!(f, "-{pre}")?;
        }
        Ok(())
    }
}

impl Ord for Version {
    fn cmp(&self, other: &Self) -> Ordering {
        self.major
            .cmp(&other.major)
            .then_with(|| self.minor.cmp(&other.minor))
            .then_with(|| self.patch.cmp(&other.patch))
            // A release outranks any prerelease of the same core (§11).
            .then_with(|| match (&self.pre, &other.pre) {
                (None, None) => Ordering::Equal,
                (None, Some(_)) => Ordering::Greater,
                (Some(_), None) => Ordering::Less,
                (Some(a), Some(b)) => compare_prerelease(a, b),
            })
    }
}

impl PartialOrd for Version {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Ordering of two versions given as strings; `None` if either does not parse.
#[must_use]
pub fn compare(installed: &str, wizard: &str) -> Option<Ordering> {
    Some(Version::parse(installed)?.cmp(&Version::parse(wizard)?))
}

fn parse_number(raw: &str) -> Option<u64> {
    if raw.is_empty() || !raw.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    raw.parse().ok()
}

fn compare_prerelease(a: &str, b: &str) -> Ordering {
    let mut a_ids = a.split('.');
    let mut b_ids = b.split('.');
    loop {
        match (a_ids.next(), b_ids.next()) {
            (None, None) => return Ordering::Equal,
            // A larger set of identifiers outranks a prefix of it.
            (None, Some(_)) => return Ordering::Less,
            (Some(_), None) => return Ordering::Greater,
            (Some(x), Some(y)) => match compare_identifier(x, y) {
                Ordering::Equal => {}
                other => return other,
            },
        }
    }
}

fn compare_identifier(a: &str, b: &str) -> Ordering {
    let numeric = |s: &str| s.chars().all(|c| c.is_ascii_digit());
    match (numeric(a), numeric(b)) {
        (true, true) => compare_numeric(a, b),
        // Numeric identifiers always have lower precedence than alphanumeric.
        (true, false) => Ordering::Less,
        (false, true) => Ordering::Greater,
        (false, false) => a.cmp(b),
    }
}

/// Digits-only comparison without overflowing: length after trimming the
/// leading zeros, then lexicographic.
fn compare_numeric(a: &str, b: &str) -> Ordering {
    let a = a.trim_start_matches('0');
    let b = b.trim_start_matches('0');
    a.len().cmp(&b.len()).then_with(|| a.cmp(b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_plain_and_prerelease() {
        assert_eq!(
            Version::parse("1.2.3").map(|v| v.to_string()),
            Some("1.2.3".into())
        );
        assert_eq!(
            Version::parse("1.2.3-beta.1").map(|v| v.to_string()),
            Some("1.2.3-beta.1".into())
        );
    }

    #[test]
    fn rejects_garbage_without_defaults() {
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
            "1.2.3-beta_1",
        ] {
            assert!(Version::parse(bad).is_none(), "{bad:?} must not parse");
        }
    }

    #[test]
    fn semver_11_prerelease_precedence() {
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
            assert_eq!(compare(pair[0], pair[1]), Some(Ordering::Less), "{pair:?}");
            assert_eq!(
                compare(pair[1], pair[0]),
                Some(Ordering::Greater),
                "{pair:?}"
            );
        }
    }

    #[test]
    fn numeric_identifiers_rank_below_alphanumeric() {
        assert_eq!(compare("1.0.0-1", "1.0.0-alpha"), Some(Ordering::Less));
    }

    #[test]
    fn huge_numeric_identifiers_do_not_overflow() {
        assert_eq!(
            compare(
                "1.0.0-99999999999999999999999",
                "1.0.0-100000000000000000000000"
            ),
            Some(Ordering::Less)
        );
    }
}
