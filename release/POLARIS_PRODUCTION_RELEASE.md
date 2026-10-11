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

## Windows replacement preflight

Before building the Windows core, the producer compiles/vets every package in
its frozen sing-tun replacement and runs the seven Windows DNS/lifecycle tests
with Go test's default vet enabled. A failed preflight stops the core build and
preserves its log. The inherited winipcfg tests used unsupported `%w` formatting
in 51 testing.Errorf calls; the separate `sing-tun-test-printf.patch` changes
only those output directives to `%v`. The source binding records both modified
baseline files and the 251 remaining byte-exact baseline files. The original
Windows auto-route patch and all production replacement code remain unchanged.
The new replacement tree requires new source/platform identities; historical
DNS/a01/mobile receipts retain their original inputs and meaning.

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

App owner has provided four-desktop layout feedback; formal identity and actual
release-consumption signoff remain pending. Mobile is a separate batch pending
App-owner API/signature and source-migration review. Android requires a real AAR with all four ABIs, actual JNI methods,
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

## Portable identity and App mapping

The original `sourceFingerprint` collector object (`fork-source-fingerprint-v1`)
retains its meaning and host observations. A separately versioned
`portableSourceIdentity` selects exactly sourceCommit, sourceTree, sourceOverlay,
goVersion, goModSha256, goSumSha256 and replacement. Its `fingerprint` is SHA256
of sorted-key, compact ASCII JSON, using the existing DNS contract canonicalizer.
`sourceIdentityFingerprint` is that same digest. Host module-list paths/digests,
Go executable hashes and evidence paths never enter the shared source identity.

`portablePlatformIdentity` hashes sourceIdentityFingerprint, os/arch, CGO_ENABLED,
sorted exact tags, version, canonical tag, Go version and sourceOverlay with the
same canonicalizer. `platformInputFingerprint` is its digest; the actual measured
BuildID must equal `polaris-production-v1-<platformInputFingerprint>`. Changed
source/version/tag/features change it; relocation or cache/tool observation
changes do not. This new schema is not the old App source-build receipt schema.

`providerContract=polaris-box-release-v1` and `providerIdentity` hash the actual
sourceCommit and source-owned producer/input file SHA256 map. Its digest is
`providerFingerprint`; this is a new actual producer identity. The App owner must
review the separate release adapter/provider-code identity and field mapping;
neither old provider `4449...` nor old source-build fingerprints are reused.
Raw BuildInfo/module graph/Go/tags/CGO/replacement facts, native library identities
and actual BuildID remain in each receipt for consumer verification.

## Explicit production publication exits

`scripts/polaris_production_publish.py` is never invoked by native CI. Its local
`prepare` mode requires the exact produced index digest and a separately reviewed
`polaris-production-approvals-v1` document binding source/version/index/scope
`six-desktop-CLI`. Source review, license/source applicability and App-owner
contract approval each need approved status, reviewer and evidence. The script
does not manufacture approvals. It snapshots exact archive bytes, updates the
outer index with a prepared annotated-tag expectation, rehashes checksums and
creates a private nine-asset publication manifest. No tag/ref/remote is created.

After the new concrete version/bytes/manifest are authorized, `stage-draft`
creates only the new exact annotated tag and fork draft, then uploads frozen
snapshots without clobber. `resume-tagged` handles an inspected exact tag with no
release; `resume-draft` requires its exact release ID and permits only missing
assets when every existing name/size/digest matches. Unexpected tags/assets stop
and are preserved. `publish` requires the exact inspected full draft ID, tag
object, source head and frozen manifest digest. It publishes a prerelease and
anonymously hashes all nine public assets. `readback` repeats the read-only
public proof. Producer readback does not sign App/mobile/device acceptance.

The nine desktop assets do not include an AAR, XCFramework, installer or final
Polaris App. Mobile four-ABI/three-slice artifacts, exact JNI and ObjC/Swift APIs,
16KiB load/final-APK checks, final PacketTunnel link/signatures and device DNS/TUN
behavior remain unverified separate delivery gates. Current App aafc/718 role
tag/provider/source manifests are unchanged. Keep the old a01 source asset until
all historical replay and new-consumer dependencies have been migrated.


Only after independent review and the one approved six-native assembly run,
prepare an externally reviewed approvals document and run the local freeze:

```sh
python3 -B scripts/polaris_production_publish.py prepare \
  --expected-head <approved-final-source-SHA> --inputs <actual-assembly-directory> \
  --index-sha256 <reviewed-actual-native-index-SHA256> \
  --approvals <reviewed-approvals.json> --approvals-sha256 <reviewed-approvals-SHA256> \
  --tag-epoch <explicit-UTC-epoch> --tagger-name <actual-tagger-name> \
  --tagger-email <actual-tagger-email> --output <fresh-external-prepared-directory>
```

Review the new prepared index/checksums/tag expectation and private manifest.
All following actions require its frozen manifest SHA256 and the same source
checkout. `stage-draft` creates the new tag/draft; it does not publish:

```sh
python3 -B scripts/polaris_production_publish.py stage-draft \
  --expected-head <approved-final-source-SHA> \
  --manifest <prepared-directory>/publication-manifest.json \
  --manifest-sha256 <reviewed-prepared-manifest-SHA256> \
  --output <fresh-external-draft-receipt.json>
```

After inspecting the resulting exact release ID and all nine draft assets,
use the same command with `publish --release-id <inspected-ID>` and a fresh
receipt path. For partial staging, use `resume-tagged` only after inspecting an
exact remote tag with no release, or `resume-draft --release-id <inspected-ID>`.
No command removes a preexisting tag/release/asset. A failed push may leave the
new local tag; inspect local and remote identity before any manual recovery.

The public readback receipt records real releaseId/assetId/URL and anonymous
size/hash checks for every uploaded asset. Its `consumerContract` selects the
four App keys and preserves each actual native receipt's provider, portable
source/platform identity, exact build inputs and archive/core/sidecar facts.
The release index digest is the actual published index digest, distinct from
its reviewed native candidate predecessor. A public release observed before a
failed download is recorded as `public-awaiting-anonymous-readback`; retry
`readback` with a fresh receipt path. A successful producer receipt still leaves
actual App download/load/carrier, mobile and device acceptance pending.
