# Bionic Wine build and release

This Wine fork owns Bionic Wine integration, the component dependency graph,
source archives, hosted dispatch and public runtime selection. Rootfs products
only download the runtime on demand. They neither build nor dispatch Wine.

The workstation entry is the Android repository's `build.ps1`; follow its
[canonical entry guide](https://github.com/taowen/arlinux/blob/main/docs/BUILD.md).
`arlinux/build.sh` and `arlinux/build/` are the implementation used by that entry
and the independent component runners. Do not create another workstation builder,
use WSL, assemble an old runtime archive, or bypass the pinned graph stages.

## Independent runtime manifests

`build/github-components.json` is the single component graph. Compiler jobs use
independent `workflow_dispatch` runs in their owning repositories, retaining each
repository's standard cache allowance. Runtime files are published beside the
producer that compiled them; there is no final combined runtime archive.

| Producer | Installable content |
|---|---|
| `wine-bionic` | Native Wine, its library closure, and paired HID/shell PE frontends |
| `wine-pe-aarch64` | ARM64/ARM64EC modules and common Wine data |
| `wine-pe-x86_64`, `wine-pe-i386` | Each architecture's Windows modules |
| `fex` | Windows CPU modules and translator policy |
| `dxvk` | DXVK modules for each architecture |
| `windows-fonts` | Immutable Windows font inputs |
| `wine-addons` | Pinned Mono/Gecko vendor archives, prepared on Windows |
| `steamworks` | Steam RPC bridge and Windows frontends |
| `windows-accessibility` | Accessibility observer |
| `windows-tray` | Windows task owner |

Each producer publishes its own `arlinux-PRODUCER.json`, checksum-addressed
archives and source records. Its completion record contains `runtimeManifest`.
SDK consumers can additionally use a verified internal compiler capsule; these
capsules are never end-user runtime downloads. The `wine-pe` merge is an internal
Steamworks SDK input. The former `wine-pe-package` and `runtime-support` runtime
assembly stages and their packaging implementation have been removed.

The local `wine-product` stage writes only `arlinux-wine-manifests.json`: a
format-2 selection of immutable producer-manifest URLs, SHA-256 values and sizes.
It never downloads or unpacks compiler capsules, recompresses runtime components,
or merges executable directories. The launcher independently downloads and caches
the selected format-1 producer manifests and their archives. It rejects conflicting
file ownership, unsafe archive paths and checksum mismatches before selecting
the installed runtime. Steam and Windows applications use the same runtime
selection and instance-owned Wine prefix.

Native packaging imports only its direct declared artifacts: compiled native
outputs and the Bionic/TLS/audio/graphics/Vulkan prefixes. It does not restore PE,
FEX/DXVK Windows modules, fonts, Mono/Gecko or their transitive compiler trees.
The native HID and Explorer frontends retain private ABI ownership with the
backend; general PE producers exclude these files to avoid overlapping installs.

## Cache and provenance

Requests hash declared source trees, recipes, locked toolchains, publication
recipes and dependency identities. A source commit is retained as provenance,
not a blanket invalidation key. Compiler outputs, references and receipts are
verified before reuse. Compiler caches are bounded in the graph; exported SDK
capsules do not duplicate complete private object trees or unrelated toolchains.

`component_inputs.py` separates runtime publication from compiler recipes.
Changing a producer manifest or PE stripping recipe republishes from verified
compiler outputs. Command-line entry guards do not enter function recipe hashes.
Changes to actual shared compiler logic still invalidate affected compile inputs.
The graph/source-identity migration requires its own first build; do not describe
that build as a steady-state warm compiler measurement.

Concurrent coordinators lock component identities and share hosted runs. Fixed
source views and product directories are isolated by commit. Immutable object
downloads resume and retain checksum verification. Cache receipts bind every
downloaded manifest and archive to the selected component record. Repeated runs
must verify outputs rather than accept a filename or an old installed instance.

The entry records `build-timing-wine.json` and `products-wine.json`. Compare exact
pins, workflow IDs, preparation, transfer, compilation and publication costs.
Repeat the complete entry to measure verified reuse; a cache hit is not evidence
of a faster fresh compilation. New independent-manifest timings and fresh-device
acceptance remain pending until recorded from the actual pipeline.

## Development validation

From the Android checkout, select a pushed full Wine commit using `build.ps1 wine`.
For deployment pass the explicit device serial and freshly installed instance.
The entry transfers verified independent manifests and archives into the existing
immutable download cache, then binds the selection SHA-256 to that stopped Debug
instance. The normal first-use installer consumes it. No latest publication or
APK rebuild is needed for subsequent Wine-only changes.

Changing the download protocol requires a consumer APK built through the same
entry. Reinstall the test Linux instance before acceptance; use the documented
authentication-only Steam backup exception, never an old prefix or home restore.
Follow the Android diagnostic guide for process maps, matching ELF hashes,
exception stacks, accessibility observations and screenshots. Finish installation,
interaction, close, relaunch and task cleanup before declaring compatibility.
Compilation or a rendered first frame alone is not acceptance.

The current foreign GDI candidate adapts Erhan Bilgili's
[Wine-Wineland transport](https://github.com/nanomatters/wine-wineland/commit/908f7702fbf6e6edb761daa47476d283e52b60f1)
in ordinary fork sources. It delivers shared-memory GDI surfaces across a child
and top-level owned by different processes, retains slots until compositor
release and updates geometry/visibility. It leaves Vulkan WSI and default GPU/
DirectComposition enabled. Power BI import/chart/save/reopen and Steam/game
regression are pending. Do not promote it based on successful builds.

## Publishing the public latest selection

Promote the exact tested `arlinux-wine-manifests.json` using the Android entry's
`publish-wine -Archive PATH -Check`, then the same invocation without `-Check`.
The publisher does not rebuild. It verifies all pinned producer manifests,
component archives, runtime file hashes, safe archive paths and corresponding
source archives before replacing the small public selection asset. Preserve
its exact SHA-256 in the release record and verify it through the normal download
path in a fresh instance.

The new asset name is `latest/arlinux-wine-manifests.json`. The previous flat
`arlinux-wine-runtime.json` and legacy `arlinux-wine-bionic.tar.gz` assets remain
frozen for earlier APKs; neither is the new publication target. Validate the new
launcher against a candidate, promote the tested selection, then release its
consumer APK. A build of immutable component objects never promotes latest.

## Optional diagnostics

`build.ps1 diagnostics` produces matching Windows exception helpers;
`build.ps1 wine-capture` produces optional Bionic GFXReconstruct tools. These
products are independent of ordinary runtime assembly and are disabled by
default. The rootfs/glibc capture product is separate. Retain capture limits,
exact module identity and an uncaptured control run; initialization records do
not establish rendered frames, successful replay or application compatibility.
