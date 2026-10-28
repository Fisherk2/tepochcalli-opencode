# `tepochcalli` PowerShell installer (T19) — HAND-WRITTEN stand-in.
#
# Gap: the `cargo dist` binary is unavailable in this environment, so this
# script (and `install.sh`) mirrors what `cargo dist build --artifacts=global`
# will generate (`installers = ["shell", "powershell"]` in `dist.toml`).
# Reconcile with `cargo dist generate --check` once `dist` is installed; M6
# still holds (no release has been published, this was never executed
# against a real release).
#
# Inspect-first caveat: NEVER run an unseen script from the internet. Fetch
# this file, read it (`irm <url> -OutFile install.ps1; notepad install.ps1`),
# and only then run it (`powershell -ExecutionPolicy Bypass -File install.ps1`).
# Nothing below executes the payload until the SHA-256 check passes.
#
# What it needs on the host: Windows PowerShell 5.1+ (in the box) with
# TLS 1.2. No Python, no Node, no package manager — the downloaded
# `tepochcalli.exe` bootstraps its own `uv` + venv (T9) and writes the MCP
# command in the portable Windows form (`venv/Scripts/python.exe`, D20).
#
# Versioning: the installer fetches the LATEST binary by default (pass
# `-Tag tepochcalli-v0.3.0` to pin one). The one-version rule lives one layer
# down: the binary always downloads the payload asset matching its OWN
# version (`tepochcalli-workspace-<ver>.tar.gz` + `.sha256`), never a
# floating `latest` (see `adapters::payload::payload_asset_url`).

param(
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

$App = "tepochcalli"
$Repo = "Fisherk2/tepochcalli-opencode"
$Target = "x86_64-pc-windows-msvc"

if ($Tag -eq "latest") {
    $Base = "https://github.com/$Repo/releases/latest/download"
} else {
    $Base = "https://github.com/$Repo/releases/download/$Tag"
}
$Archive = "$App-$Target.zip"

# TLS 1.2 (old Windows PowerShell defaults to 1.0 and the handshake fails).
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Work = Join-Path ([IO.Path]::GetTempPath()) ("$App-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Work | Out-Null
try {
    Write-Host "install.ps1: downloading $Archive ($Tag)…"
    Invoke-WebRequest -Uri "$Base/$Archive" -OutFile (Join-Path $Work $Archive)
    Invoke-WebRequest -Uri "$Base/$Archive.sha256" -OutFile (Join-Path $Work "$Archive.sha256")
    # The sidecar is `sha256sum` format (`<hex>  <filename>`); compare the
    # hash only (the filename inside may carry a different prefix).
    $Expected = ((Get-Content (Join-Path $Work "$Archive.sha256") -Raw) -split '\s+')[0]
    $Actual = (Get-FileHash -Path (Join-Path $Work $Archive) -Algorithm SHA256).Hash.ToLower()
    if ($Expected.ToLower() -ne $Actual) {
        Write-Error "install.ps1: CHECKSUM MISMATCH for $Archive (expected $Expected, got $Actual)"
        exit 1
    }
    Expand-Archive -Path (Join-Path $Work $Archive) -DestinationPath $Work -Force
    # The verified tree is checksummed; execution starts only here.
    & (Join-Path $Work "$App.exe") @args
    exit $LASTEXITCODE
} finally {
    # Best-effort: residue is an inert, checksummed archive + binary.
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
