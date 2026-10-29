#!/bin/sh
# `tepochcalli` shell installer (T19) — HAND-WRITTEN stand-in.
#
# Gap: the `cargo dist` binary is unavailable in this environment, so this
# script (and `install.ps1`) mirrors what `cargo dist build --artifacts=global`
# will generate (`installers = ["shell", "powershell"]` in `dist.toml`).
# Reconcile with `cargo dist generate --check` once `dist` is installed; M6
# still holds (no release has been published, these were never executed
# against a real release).
#
# Inspect-first caveat: NEVER pipe an unseen script into `sh`. Fetch this
# file, read it (`curl -fsSL <url> -o install.sh && less install.sh`), and
# only then run it (`sh install.sh`). The script itself changes nothing until
# the checksum below verifies.
#
# What it needs on the host: POSIX `sh`, `curl`, `tar`, and ONE of
# `sha256sum` / `shasum`. No Python, no Node, no package manager — the
# downloaded `tepochcalli` binary bootstraps its own `uv` + venv (T9).
#
# Versioning: the installer fetches the LATEST binary by default (pass a tag
# like `tepochcalli-v0.3.0` as `$1` to pin one). The one-version rule lives
# one layer down: the binary always downloads the payload asset matching its
# OWN version (`tepochcalli-workspace-<ver>.tar.gz` + `.sha256`), never a
# floating `latest` (see `adapters::payload::payload_asset_url`).

set -eu

APP="tepochcalli"
REPO="Fisherk2/tepochcalli-opencode"
TAG="${1:-latest}"
# Seam for tests/mirrors: override the release base URL; unset keeps the real one.
BASE_URL="${TEPOCHCALLI_RELEASE_BASE_URL:-}"

usage() {
    echo "usage: install.sh [tag] [-- inspect-first: read this script before running it]" >&2
    echo "example: sh install.sh tepochcalli-v0.3.0" >&2
}

detect_target() {
    os="$(uname -s)"
    arch="$(uname -m)"
    case "${os}-${arch}" in
        Linux-x86_64) echo "x86_64-unknown-linux-gnu" ;;
        Linux-aarch64 | Linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
        Darwin-x86_64) echo "x86_64-apple-darwin" ;;
        Darwin-aarch64 | Darwin-arm64) echo "aarch64-apple-darwin" ;;
        *) echo "unsupported platform: ${os}-${arch} (see usage)" >&2; usage; exit 1 ;;
    esac
}

need() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "install.sh: missing required tool: $1" >&2
        exit 1
    }
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "install.sh: need sha256sum or shasum to verify the download" >&2
        exit 1
    fi
}

fetch() {
    # https pins the protocol; a non-https override (loopback mirror) cannot be pinned.
    case "$1" in
        https://*) curl --proto '=https' --tlsv1.2 -fsSL "$1" -o "$2" ;;
        *) curl -fsSL "$1" -o "$2" ;;
    esac
}

main() {
    need curl
    need tar
    need awk
    # `$1` (when present) is the release tag; the rest forwards to the binary.
    if [ $# -gt 0 ]; then shift; fi
    target="$(detect_target)"
    if [ -n "${BASE_URL}" ]; then
        base="${BASE_URL}"
    elif [ "${TAG}" = "latest" ]; then
        base="https://github.com/${REPO}/releases/latest/download"
    else
        base="https://github.com/${REPO}/releases/download/${TAG}"
    fi
    archive="${APP}-${target}.tar.gz"
    work="$(mktemp -d)"
    # shortcut: no trap on pre-POSIX `mktemp -d` failures; the dir is empty
    # until the verified extract below, and residue is inert.
    echo "install.sh: downloading ${archive} (${TAG})…" >&2
    fetch "${base}/${archive}" "${work}/${archive}"
    fetch "${base}/${archive}.sha256" "${work}/${archive}.sha256"
    # The sidecar is `sha256sum` format (`<hex>  <filename>`); compare the
    # hash only (the filename inside may carry a different prefix).
    expected="$(awk '{print $1}' "${work}/${archive}.sha256")"
    actual="$(sha256_of "${work}/${archive}")"
    if [ "${expected}" != "${actual}" ]; then
        echo "install.sh: CHECKSUM MISMATCH for ${archive}" >&2
        echo "  expected: ${expected}" >&2
        echo "  actual:   ${actual}" >&2
        exit 1
    fi
    tar -xzf "${work}/${archive}" -C "${work}"
    # The verified tree is checksummed; execution starts only here.
    exec "${work}/${APP}" "$@"
}

main "$@"
