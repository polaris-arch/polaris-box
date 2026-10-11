# Polaris-box production distribution contract

The planned version is `1.15.0-alpha.12.polaris.1`, with tag
`v1.15.0-alpha.12.polaris.1`. It keeps the upstream alpha.12 baseline and
the reviewed Polaris patches. The tag, kernel-reported version, archive name,
archive root and asset index use this same version. No existing tag is moved.
This producer emits candidates; no public release is created by the workflow.
The alpha.11/alpha.12 endpoint delta is limited to the upstream build workflow
and changelog. Runtime/module/Cronet/preset trees are identical; all Polaris
runtime patches remain byte-preserved. The aggregate source is a normal merge
with alpha.12 ancestry. Fork `testing` and upstream `testing` have diverged
history; this batch does not force-update that mirror.

## Desktop layout

Linux and macOS use `polaris-box-<version>-<os>-<arch>.tar.gz`; Windows uses
`.zip`. Each archive has one root with the same basename. The internal executable
remains `sing-box` or `sing-box.exe`. Root `LICENSE`, `licenses/`, `provenance.json`,
`source/SOURCE-INDEX.json` and `SHA256SUMS` accompany the executable.

Linux amd64/arm64 includes `libcronet.so`; Windows amd64/arm64 includes
`libcronet.dll`. macOS amd64/arm64 statically links the fixed downloaded Cronet
archive during the kernel build and needs no dynamic Cronet sidecar. The existing
prebuilt Cronet inputs are hash/size/module-origin pinned. This workflow does not
compile Chromium/Cronet again. Every kernel is built afresh from its actual
fixed source SHA with Go 1.25.5, its final version, VCS metadata and measured BuildID.

`polaris-box-assets.json` records every archive and member digest, source/tree,
source-owned replacement fingerprint, actual Go module graph, platform/tags,
BuildID, Cronet version/linkage and observed signature state. The outer
`SHA256SUMS` covers the six archives, standalone source archive and asset index.
Expected hashes must be frozen by the consumer review before downloading.

The four existing Polaris targets map to Linux amd64 (`linux`), Windows amd64
(`win`), macOS amd64 (`mac-x64`) and macOS arm64 (`mac-arm64`). Linux/Windows
arm64 are additional CLI distributions and are not implicitly new App targets.
The other 38 upstream CLI archives, 31 Linux packages and 64 OpenWrt packages
are not produced by this workflow. SFA/SFI/SFL/SFM/SFW are upstream clients;
their 29 assets cannot be relabeled as Polaris App packages.

## Consumer verification

The App owner maintains the consumer manifest/download adapter separately from
the frozen FK02 source producer. An accepted consumer obtains the real release
from the allowlisted repository, checks its frozen tag object/source identity
and expected archive digest/size, safely unpacks the exact root, checks the
kernel/library member digests and target architecture, then verifies version,
BuildID, source/replacement fingerprint and feature tags. It loads the explicit
bundled Cronet path and runs the actual core/Cronet checks before accepting the
new carrier. Missing libraries, wrong architecture/version, tampered bytes or
unapproved signatures fail before use. Users do not build the core or supply
libraries. The source archive is not a runtime kernel or a download fallback.

Current producer receipts and the aggregate index keep publication and consumer
acceptance pending. Native Cronet diagnostics do not prove real TUN/VpnService/
PacketTunnel traffic. macOS final App signatures, mobile final links/devices,
independent notice/source applicability and compiler-injected runtime review
require their own actual evidence. Historical flags in retained a01 source
inputs are preserved; they do not claim acceptance for this version.

## Standalone source replay

`polaris-box-<version>-source.tar.gz` contains `core-source.tar` for the actual
new fixed commit (including the full source-owned sing-tun replacement), a new
source index with the actual six-platform module union, this recipe and the
exact retained `reused-inputs.tar.gz`. The retained package includes module
source ZIPs, Go standard-library source, notices and pinned Cronet/NaiveProxy
source/build materials. Assembly verifies each actual module source ZIP and
component source archive. Downloading the new standalone source asset is
sufficient for replay; its nested input does not require the old release URL.

After verifying the new standalone source asset against its reviewed expected
SHA256, recover its original retained input without fetching the old release:

```sh
python scripts/polaris_production_release.py recover-source \
  --source ./polaris-box-1.15.0-alpha.12.polaris.1-source.tar.gz \
  --source-archive-sha256 <reviewed-new-source-asset-sha256> \
  --expected-head <actual-new-source-commit> \
  --output ./polaris-box-a01-desktop-source-candidate-six-platforms-v4.tar.gz
```

The first production assembly still fetches the old immutable retained input;
later replay can use the nested bytes above. Existing frozen DNS publication
scripts continue to reference the a01 source asset and must retain that asset
until their historical replay/migration contract is separately closed.

## Mobile delivery

The mobile contract is pending App-owner API/signature and source-migration
review. Android requires a real AAR with all four ABIs, actual JNI methods,
API24 minimum, 16KiB load alignment and the approved NDK/gomobile versions.
iOS requires a static XCFramework containing device arm64 and both simulator
slices. The App packaging pipeline downloads/verifies and statically links it,
including the PacketTunnel final link. A static iOS library is never treated as
an install-time downloadable runtime library. Existing alpha.8 mobile sources
and receipts remain unchanged. No mobile assets are emitted or marked accepted
by the desktop workflow.

## Release and cleanup gates

The workflow is manual, native-only, max-parallel two, and cannot write tags,
release metadata or release assets. Optional build provenance is generated only
on the approved `polaris-main` revision with the explicit `attest` input.
Provenance generation is not publication or independent review. Public
publication requires separately reviewed frozen source, all actual platform
proofs, corresponding-source/notice review, App-owner contract signoff, asset
index/checksum verification and a separately authorized publish step. Do not
rename existing binary bytes to this version or overwrite/move used tags.

Keep `polaris-v1.15.0-alpha.11-2` while FK02 consumes its exact aafc tag object.
Keep the a01 source asset while old DNS acquisition/replay instructions refer
to it. Only after the new real-release consumer chain succeeds and all old
dependencies are addressed may a precise obsolete-asset subset be reviewed for
cleanup. Restorable bytes do not preserve deleted GitHub release IDs or counters.
