# Release Process

This document describes how installers, signatures and auto-updates are
produced (feature release-017). Items marked TODO are not yet executable
in this workspace and are listed in `feature_list.json` as the remaining
verification steps.

## 1. Build the sidecar (per OS/architecture)

```sh
./scripts/build-sidecar.sh <target-triple>
```

One binary per platform, e.g. `x86_64-unknown-linux-gnu`,
`x86_64-pc-windows-msvc`, `aarch64-apple-darwin`. CI
(`.github/workflows/build.yml`) runs this on all three runners.

## 2. Build installers

```sh
npm run tauri build
```

The PyInstaller sidecar is bundled via `externalBin`
(`src-tauri/tauri.conf.json`) and installed next to the main executable.

## 3. Signing keys (TODO)

Tauri v2 uses minisign-style keys for updater artifacts:

```sh
npm run tauri signer generate -- -w ~/.tauri/stage-finder.key
```

- Private key + passphrase: secrets of the release infrastructure
  (`TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`).
  Never in the repository.
- Public key: set in `bundle.windows.certificateThumbprint` (Windows
  code signing) and `plugins.updater.pubkey`.

Steps remaining (require the maintainer's signing identities):
1. Generate the updater key pair and fill `plugins.updater.pubkey` in
   `tauri.conf.json`.
2. Windows: obtain an EV/OV code-signing certificate and set
   `bundle.windows.certificateThumbprint`.
3. macOS: join the Apple Developer Program, configure
   `bundle.macOS.signingIdentity` and notarization credentials.

## 4. Auto-update (TODO)

`tauri.conf.json` declares the updater plugin with:
`createUpdaterArtifacts: true` and an `updater` endpoint
(`https://<updates-host>/{{target}}/{{current_version}}`).

Remaining steps:
1. Add the `tauri-plugin-updater` Rust dependency and register it in
   the core (small change, blocked on having a real update server and
   signed artifacts to test against).
2. Host a JSON update manifest (latest.json) describing the signed
   artifacts per platform.
3. Publish v1, then verify an update from v1 to v2 actually works
   (`feature_list.json` → release-017 verification).

## 5. User documentation

- `README.md`: setup, development, verification.
- `docs/USER.md`: end-user guide (profile, search, matching, review,
  delivery with the mandatory confirmation, tracking, privacy, language).
