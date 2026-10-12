# Polaris-box production distribution contract

The new planned title/version is `1.15.0-alpha.12`, tag `v1.15.0-alpha.12`. The core-reported version, archive name/root, package source identity and asset index align with that version. The existing `v1.15.0-alpha.12.polaris.1` release remains immutable while the active Polaris consumer migrates. Do not move its tag or relabel its original bytes.

This batch covers six desktop CLI archives and four OpenWrt packages. The four existing App targets remain Linux amd64 (`linux`), Windows amd64 (`win`), macOS amd64 (`mac-x64`) and macOS arm64 (`mac-arm64`). Extra Linux/Windows ARM64 CLI rows and OpenWrt rows do not create new App targets. Mobile AAR/XCFramework, other upstream architecture variants, upstream client applications and final Polaris carriers are separate agreed scopes.

## Layout and capabilities

Desktop roots are exactly `polaris-box-<version>-<os>-<arch>`. Linux/macOS use `.tar.gz`; Windows `.zip`; executables remain `sing-box` / `sing-box.exe`. Linux/Windows include the fixed prebuilt Cronet `.so` / `.dll` in the same archive. macOS statically links its fixed prebuilt Cronet archive. All six cores are freshly built from the actual final source, Go1.25.5, exact full feature tags and measured source-derived BuildID. The original module name, 256-file modified local sing-tun source and existing Polaris patches remain intact. Windows replacement regressions retain full-package vet and the seven existing platform tests.

OpenWrt assets are `polaris-box-<version>-openwrt-<architecture>.ipk/.apk`. Architectures are `x86_64` (GOAMD64=v1) and `aarch64_generic` (GOARM64=v8.0). IPK targets OpenWrt24.10/opkg; APK targets25.12/apk3. The fixed musl `.a` is linked with CGO1, `with_musl`, `with_naive_outbound`, `with_gvisor` and the existing full preset; `with_purego` is forbidden. Clang CC/CXX use the exact OpenWrt target/sysroot and LLD contract; SDK, Clang archive, GCC runtime/musl and Cronet pins are source-owned. No Chromium rebuild, desktop glibc library or OpenSSL replacement is used. [OpenWrt installation and migration](POLARIS_OPENWRT.md) documents dependencies, explicit conflicts, disabled defaults, configuration retention and recovery.

## Whole-batch remote validation

Polaris-box already has remote CI. Complete the batch's feature/interface/build/package/publisher code together, then commit/push once to the authorized batch branch. Review the whole candidate and aggregate issues; complete related corrections before the next unified verification. Compiler failures, including interface/design errors, have no single-change build/test/CI exception. Do not compile locally or start per-feature CI. Existing valid runs remain untouched; final necessary gates still require the accurate candidate SHA.

The manual production workflow runs the Python/source contract suite, six native desktop builds, two actual static musl core/package builds, four official isolated OpenWrt guest lifecycle/runtime gates and same-run assembly. Each core requires clean standalone source and actual BuildInfo/BuildID. Guests verify generic CPU profiles, official kernel/root hashes, real package dependencies, conflict rejection, install/active upgrade/configuration retention/removal/reinstall, procd, CA-bundle, real Naive TLS-H2 plus wrong-CA rejection, and actual gVisor TUN traffic. User-mode VM networking is isolated; no physical device, host TAP or host routes are changed. Actual guest checks do not certify every board/CPU or replace physical-device acceptance.

The aggregate index keeps `platforms` as the original six desktop producer rows and records OpenWrt separately in `openwrtPlatforms`. Same source/tree/version/run/attempt and actual archive/core/package bytes must match. Formal native CI cannot be replaced by old local fixtures or historical green runs. Candidate publication remains false until the parent approves the whole source/license/layout and actual output batch.

## Corresponding source

No separately uploaded source package is generated. Automatic GitHub Source code archives provide the fixed product source, including the complete modified replacement. `sourceDelivery` provides exact public Go module ZIP/h1 pins, Go distribution source, fixed driver/engine Git trees (including gitlink and archive omissions), and GCC/musl sources with the exact OpenWrt source/patch tree and runtime exception. Same-run assembly verifies full module/source bytes and exact Git blobs. The distributor remains responsible for equivalent copying access and ongoing availability under applicable licenses. A homepage or prebuilt-library ZIP alone does not supply the engine's corresponding source.

## Explicit publication

The build workflow has read-only repository permissions and never tags or publishes. After whole-batch review of the actual final index and required source/platform outputs, retain the parent's actual review message as raw, hash-pinned evidence bound to the exact source/index. Do not manufacture an approval JSON from CI success. `polaris_production_publish.py prepare` freezes exactly twelve upload assets: six desktop archives, four OpenWrt packages, `polaris-box-assets.json`, `SHA256SUMS`. It prepares an annotated tag object and title `1.15.0-alpha.12`; no remote write occurs during preparation.

Explicit `stage-draft` creates only the new exact tag and draft, `resume-*` uploads missing immutable assets only, and `publish` requires the exact complete inspected draft. All twelve final public assets are downloaded anonymously and checked in full against the frozen expected sizes/hashes; release/asset IDs and canonical URLs are captured with tag/source/tree before and after readback. `consumerContract` projects the original four App rows with actual published index/asset IDs and keeps App/mobile/device/signature trust pending. New production App pins are separately owned by the App integrator and must originate from these final bytes.

Existing in-use tags/releases remain available until the actual consumer migration closes. No automatic cleanup, tag movement, upstream write, deployment or physical-network change is part of this producer/publisher.
