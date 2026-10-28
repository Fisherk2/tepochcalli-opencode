//! OM-1 spike tests: 4 attack classes x (tar.gz + zip) must be REJECTED
//! with typed errors BEFORE any disk write (dest dir stays intact).
//!
//! Plus one positive test per format: valid nested archives extract fine.

use std::fs;
use std::io::Write;
use std::path::Path;

use flate2::write::GzEncoder;
use tepochcalli::archive::{extract_tar_gz, extract_zip, ArchiveError};

// --- archive builders (in-memory, malicious by construction) ---

#[derive(Clone, Copy)]
enum Member {
    File(&'static str),
    Symlink(&'static str),
}

fn write_octal(buf: &mut [u8], value: u64) {
    // ASCII octal, zero-padded, NUL-terminated (ustar convention).
    buf.fill(b'0');
    let s = format!("{value:o}");
    let digits = s.as_bytes();
    let start = buf.len() - digits.len() - 1;
    buf[start..start + digits.len()].copy_from_slice(digits);
    buf[buf.len() - 1] = 0;
}

/// Raw ustar builder: `tar::Builder` refuses malicious names at build time,
/// but attackers hand-craft bytes — so do the tests.
fn raw_tar_gz_bytes(members: &[(&str, Member)]) -> Vec<u8> {
    let mut tar_data = Vec::new();
    for (name, member) in members {
        let mut header = [0u8; 512];
        let name_bytes = name.as_bytes();
        header[..name_bytes.len()].copy_from_slice(name_bytes);
        write_octal(&mut header[100..108], 0o644);
        write_octal(&mut header[108..116], 0);
        write_octal(&mut header[116..124], 0);
        let (typeflag, linkname, size) = match member {
            Member::File(content) => (b'0', "", content.len() as u64),
            Member::Symlink(target) => (b'2', *target, 0),
        };
        write_octal(&mut header[124..136], size);
        write_octal(&mut header[136..148], 0);
        header[148..156].fill(b' ');
        header[156] = typeflag;
        let link_bytes = linkname.as_bytes();
        header[157..157 + link_bytes.len()].copy_from_slice(link_bytes);
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        let checksum: u32 = header.iter().map(|b| *b as u32).sum();
        let chk = format!("{checksum:06o}\0 ");
        header[148..156].copy_from_slice(chk.as_bytes());
        tar_data.extend_from_slice(&header);
        if let Member::File(content) = member {
            tar_data.extend_from_slice(content.as_bytes());
            let pad = 512 - content.len() % 512;
            if pad < 512 {
                tar_data.extend(std::iter::repeat_n(0, pad));
            }
        }
    }
    tar_data.extend(std::iter::repeat_n(0, 1024)); // end-of-archive
    let mut enc = GzEncoder::new(Vec::new(), flate2::Compression::fast());
    enc.write_all(&tar_data).unwrap();
    enc.finish().unwrap()
}

fn zip_bytes(members: &[(&str, Member)]) -> Vec<u8> {
    let mut buf = std::io::Cursor::new(Vec::new());
    let mut writer = zip::ZipWriter::new(&mut buf);
    let file_opts = zip::write::SimpleFileOptions::default().unix_permissions(0o644);
    for (name, member) in members {
        // Symlink bit included: `unix_permissions` keeps only the low bits,
        // the file-type fixup happens below in `mark_central_dir_symlink`.
        let content = match member {
            Member::File(content) => *content,
            Member::Symlink(target) => *target,
        };
        writer.start_file(*name, file_opts).unwrap();
        writer.write_all(content.as_bytes()).unwrap();
    }
    drop(writer);
    let mut bytes = buf.into_inner();
    if members.iter().any(|(_, m)| matches!(m, Member::Symlink(_))) {
        mark_central_dir_symlink(&mut bytes);
    }
    bytes
}

/// `unix_permissions(0o120777)` drops the file-type bits, so real symlink
/// entries (S_IFLNK in the central directory) are patched in by hand —
/// exactly what an attacker-crafted zip looks like.
fn mark_central_dir_symlink(bytes: &mut [u8]) {
    const SIG: [u8; 4] = [0x50, 0x4b, 0x01, 0x02]; // PK\x01\x02
    const EXTERNAL_ATTRS: usize = 38;
    let patched: [u8; 4] = (0o120777u32 << 16).to_le_bytes();
    for i in 0..bytes.len().saturating_sub(EXTERNAL_ATTRS + 4) {
        if bytes[i..i + 4] == SIG {
            bytes[i + EXTERNAL_ATTRS..i + EXTERNAL_ATTRS + 4].copy_from_slice(&patched);
        }
    }
}

// --- harness: dest with a sentinel; assert intact after rejection ---

fn intact_dest() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("sentinel.txt"), "user data").unwrap();
    dir
}

fn assert_dest_intact(dir: &tempfile::TempDir) {
    let entries: Vec<_> = fs::read_dir(dir.path())
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .collect();
    assert_eq!(entries, vec![std::ffi::OsString::from("sentinel.txt")]);
    assert_eq!(
        fs::read_to_string(dir.path().join("sentinel.txt")).unwrap(),
        "user data"
    );
}

fn is_rejection(err: &ArchiveError) -> bool {
    matches!(
        err,
        ArchiveError::Traversal { .. }
            | ArchiveError::AbsolutePath { .. }
            | ArchiveError::WindowsPath { .. }
            | ArchiveError::UnsafeSymlink { .. }
    )
}

// --- attack matrix ---

const ATTACKS: &[(&str, Member)] = &[
    ("../evil.txt", Member::File("pwned")),
    ("/abs.txt", Member::File("pwned")),
    ("C:\\win.txt", Member::File("pwned")),
    ("link", Member::Symlink("/etc/passwd")),
];

#[test]
fn tar_gz_rejects_traversal_before_write() {
    let dir = intact_dest();
    let data = raw_tar_gz_bytes(&[ATTACKS[0]]);
    let err = extract_tar_gz(&data[..], dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn tar_gz_rejects_absolute_posix_before_write() {
    let dir = intact_dest();
    let data = raw_tar_gz_bytes(&[ATTACKS[1]]);
    let err = extract_tar_gz(&data[..], dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn tar_gz_rejects_absolute_windows_before_write() {
    let dir = intact_dest();
    let data = raw_tar_gz_bytes(&[ATTACKS[2]]);
    let err = extract_tar_gz(&data[..], dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn tar_gz_rejects_absolute_symlink_before_write() {
    let dir = intact_dest();
    let data = raw_tar_gz_bytes(&[ATTACKS[3]]);
    let err = extract_tar_gz(&data[..], dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn zip_rejects_traversal_before_write() {
    let dir = intact_dest();
    let data = zip_bytes(&[ATTACKS[0]]);
    let err = extract_zip(std::io::Cursor::new(&data[..]), dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn zip_rejects_absolute_posix_before_write() {
    let dir = intact_dest();
    let data = zip_bytes(&[ATTACKS[1]]);
    let err = extract_zip(std::io::Cursor::new(&data[..]), dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn zip_rejects_absolute_windows_before_write() {
    let dir = intact_dest();
    let data = zip_bytes(&[ATTACKS[2]]);
    let err = extract_zip(std::io::Cursor::new(&data[..]), dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn zip_rejects_absolute_symlink_before_write() {
    let dir = intact_dest();
    let data = zip_bytes(&[ATTACKS[3]]);
    let err = extract_zip(std::io::Cursor::new(&data[..]), dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn tar_gz_rejects_relative_symlink_escape() {
    // `..` target: escapes without being absolute.
    let dir = intact_dest();
    let data = raw_tar_gz_bytes(&[("sub/link", Member::Symlink("../../outside"))]);
    let err = extract_tar_gz(&data[..], dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

#[test]
fn zip_rejects_dotdot_prefix_member() {
    // `sub/../../evil`: `..` hidden after a legit prefix.
    let dir = intact_dest();
    let data = zip_bytes(&[("sub/../../evil.txt", Member::File("pwned"))]);
    let err = extract_zip(std::io::Cursor::new(&data[..]), dir.path()).unwrap_err();
    assert!(is_rejection(&err), "unexpected: {err:?}");
    assert_dest_intact(&dir);
}

// --- positive cases: valid nested archives extract correctly ---

fn valid_members() -> Vec<(&'static str, Member)> {
    vec![
        ("docs/", Member::File("")),
        ("docs/note.md", Member::File("# hello")),
        ("docs/sub/deep.txt", Member::File("deep")),
    ]
}

fn is_dir_member(name: &str) -> bool {
    name.ends_with('/')
}

#[test]
fn tar_gz_extracts_valid_nested_archive() {
    let all = valid_members();
    let files: Vec<(&str, Member)> = all.into_iter().filter(|(n, _)| !is_dir_member(n)).collect();
    // tar dir entries: append a real dir member via path ending in '/'
    let enc = GzEncoder::new(Vec::new(), flate2::Compression::fast());
    let mut builder = tar::Builder::new(enc);
    builder.append_dir("docs", Path::new(".")).unwrap();
    for (name, member) in &files {
        let Member::File(content) = member else {
            unreachable!()
        };
        let mut header = tar::Header::new_gnu();
        header.set_size(content.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        builder
            .append_data(&mut header, name, content.as_bytes())
            .unwrap();
    }
    let data = builder.into_inner().unwrap().finish().unwrap();

    let dir = tempfile::tempdir().unwrap();
    extract_tar_gz(&data[..], dir.path()).unwrap();
    assert_eq!(
        fs::read_to_string(dir.path().join("docs/note.md")).unwrap(),
        "# hello"
    );
    assert_eq!(
        fs::read_to_string(dir.path().join("docs/sub/deep.txt")).unwrap(),
        "deep"
    );
}

#[test]
fn zip_extracts_valid_nested_archive() {
    let files: Vec<(&str, Member)> = valid_members()
        .into_iter()
        .filter(|(n, _)| !is_dir_member(n))
        .collect();
    let data = zip_bytes(&files);
    let dir = tempfile::tempdir().unwrap();
    extract_zip(std::io::Cursor::new(&data[..]), dir.path()).unwrap();
    assert_eq!(
        fs::read_to_string(dir.path().join("docs/note.md")).unwrap(),
        "# hello"
    );
    assert_eq!(
        fs::read_to_string(dir.path().join("docs/sub/deep.txt")).unwrap(),
        "deep"
    );
}
