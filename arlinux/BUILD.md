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

This section describes internal compiler products and candidate provenance,
not the public update protocol. User downloads use the fixed component releases
documented under [Publishing fixed component releases](#publishing-fixed-component-releases).

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

FEX is pinned to the taowen/FEX fork commit
`371b6f6dc4086321ee53ec9cf032615476389f51`, retaining the ARM64EC
process-termination fix `b63017afe` removed by Wine integration commit
`318936f` and applying the same lock lifetime to WoW64 termination.
Before terminating peer threads, it drains code invalidation and retains the
locks across the termination notification. The WoW64 change follows the
observed .NET service's detach/unmap wait with a stranded invalidation reader;
fresh-instance Power BI validation remains required. Keep such component fixes
in the pinned fork rather than applying patches during builds.

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
of a faster fresh compilation.

On 2026-10-20, candidate `30b74024f6aedb153503486fc95fc4552300fd77`
completed the independent-manifest pipeline. Its 3,716-byte selection has SHA-256
`0a3e0a629aa373950f65d5b5d53a3d7ea6736e08137315ba59ad7ef94c32a59e`.
The native runtime components total 17.74 MiB; PE, vendor and support downloads
are separate. The first publication/recovery run took 1,204.86 seconds, including
1,096.875 seconds graph work and the initial runtime transfers. Repeating the
complete coordinator for the identical pin took 3.328 seconds, including 2.609
seconds graph work, with no new hosted job or runtime download. This excludes
device seeding and is verified reuse, not a fresh compiler benchmark.

The corrected consumer APK used rootfs
`7e7b406d8e860fe7c8b089ccffdd86e35232ecc2`; installed APK SHA-256 was
`cdc7d1238390f8df3355a96e386b439de44b19d2fbf9a54dddbe16a9c4ba4a49`.
Xiaomi 15 (`3fad759`), fresh instance `yibu-62fb6886`, passed built-in FontForge
first-use runtime installation, vendor installation, typed Arial opening, visible
glyph rendering, SFD save, normal quit, icon relaunch with the saved SFD and final
quit. Live native mappings identified the exact selection above. This validates
the split installation journey; it does not establish Power BI/WebView2 or game
compatibility. Those regressions and public latest promotion remain pending.

## Development validation

From the Android checkout, select a pushed full Wine commit using `build.ps1 wine`.
For deployment pass the explicit device serial and freshly installed instance.
The entry transfers only verified selection/producer metadata and binds the
selection SHA-256 to that stopped Debug instance. The normal first-use installer
downloads archives directly from GitHub into the instance-external immutable
cache, verifies SHA-256 and reuses matching cached bytes. Runtime payloads do not
travel through Windows or ADB. No latest publication or
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

## Publishing fixed component releases

Public runtime distribution uses one fixed release tag per producer, in that
producer's repository: `arlinux-PRODUCER-latest`, containing `runtime.tar.gz`.
Create a tag only on its first publication; subsequent updates replace the asset
in place. Neither a public total-selection JSON nor public producer JSON files
are needed. GitHub's release API supplies the current asset SHA-256, size and ID.
Each archive carries its own `bionic-runtime.json` with file/source provenance.
The consumer's endpoint list is `windows-downloads.tsv`, not a set of hash pins.

Private Wine/PE/FEX/Steamworks interfaces carry a matching compatibility identity.
Data-only fonts/addons and Vulkan clients are independently updateable. A
consumer snapshots release assets, verifies downloads and embedded metadata,
rejects incompatible component snapshots/duplicate ownership and installs into
a new immutable runtime directory before changing its current pointer.
An update-in-progress may fail and be retried; it must never select a partial mix.

The internal build graph still publishes content-addressed compiler objects and
producer receipts for reproducibility and cached SDK consumers. Those are build
records, not the public update protocol. Do not replace compiler-cache identities
with mutable latest tags. The old monolithic `latest` assets remain untouched.

Run from the Windows Android checkout using its sole `build.ps1` entry. Retain
the exact verified product directory from `build.ps1 wine`; this contains the
declared producer outputs, not an installed instance or an old runtime export.
Pin the publisher revision as well as the compiler product. The publisher
preflight verifies the pinned metadata and dispatches the release-only job in each
producer's owning repository. Those standard x64 runners verify runtime/source
hashes and package deterministic delivery archives. They never run compiler setup,
restore compiler caches or compile Wine. The workstation retains only candidate
metadata/receipts in the product's `public-release/` directory.

Each producer has a fixed `arlinux-PRODUCER-candidates` Release. Candidate assets
are keyed by the pinned inputs, compatibility identity and packaging recipe;
existing assets are immutable and reusable. The canonical workflow wrapper is
installed/updated through the publisher before dispatch. Every owner uses its
own `github.token`; no personal access token is copied to a runner or phone.

```powershell
$wineRef = 'FULL_PUBLISHER_COMMIT'
$wineSelection = 'EXACT_VERIFIED_PRODUCT_DIRECTORY/arlinux-wine-manifests.json'
.\build.ps1 publish-wine -WineRef $wineRef -Archive $wineSelection -Check -Serial SERIAL -Instance yibu-FRESH_INSTANCE
```

Here `-Archive` identifies the internal build selection, not a public download.
With a stopped fresh Debug instance, `-Check -Serial -Instance` transfers only
the small internal candidate receipt and binds its SHA-256 to that instance.
The phone's ordinary first-use installer downloads the immutable candidate
assets directly, with the same cache, GitHub route policy and SHA-256 validation
as normal downloads. Without device arguments the command only prepares/verifies
publication candidates on runners. It does not update public latest. Complete the real install/input/close/
relaunch/task-stop journey before promotion; compilation alone is not acceptance.
Keep the publication candidate digest, source product, consumer APK and evidence.

```powershell
.\build.ps1 publish-wine -WineRef $wineRef -Archive $wineSelection
```

Promotion verifies the tested candidate receipt against the input selection and
dispatches only the owner repository's release job. Each runner downloads the
exact tested candidate by SHA-256 and replaces only changed `runtime.tar.gz`
assets in its fixed public Release. It never repackages or rebuilds during
promotion. Windows sends only workflow requests and reads completion/digests;
it never downloads/uploads candidate runtime payloads. Compiler success alone
does not trigger promotion: explicit device acceptance remains the release gate.
No release is created for an unchanged or subsequent version of a producer.
Source references use the already published checksum-addressed source objects.

After promotion, compare every public asset digest/size with the prepared
product, then use a new instance with no candidate override. Normal launch must
resolve GitHub releases and select the same component archive hashes, using verified
shared downloads where available. Do not write latest cache state manually or
restore an old prefix. Retain actual process maps and finish the application/
game journey again. Existing successful lookups expire after one hour; a fresh
instance verifies publication without that previous-instance cache.
The local selection receipt hash can differ between candidate and public paths
because their URLs differ; compare the component hashes and embedded metadata,
not only that receipt filename.
An interrupted upload or incompatible snapshot is not permission to use the
frozen legacy bundle. A consumer APK/distribution update is required for this
new protocol; an APK upgrade alone does not replace an existing rootfs's scripts.

Runner packaging verification on 2026-10-20 used producer inputs from Wine
integration `6ae74513401427716cc81b83dc70797b48ee8879`. Hashing each tar member
while copying it removed gzip rewinds: the i386 release job changed from 315
seconds (run `39382419742`) to 24 seconds (run `39383104749`). Both produced
the identical 77,981,623-byte archive SHA-256
`158696aac158668a5188786fda7171f3f26c67e1271dad9ffa9c92ce18bc2ba6`.
These are candidate packaging/job timings, not compiler or whole-graph timings.

The runner-only publication was exercised for all 11 producers using publisher
`5e034d293e16d8c7d7df68ca7d759269f1e40b40`. Candidate and public assets matched
the previously tested archives exactly (569,209,277 bytes total). For example,
promotion run `39383641288` executed only the release job; no compiler work,
workstation runtime download/upload or repackaging occurred. All public digests
were checked again after completion.

X300 USB `10AFA31610002QH`, fresh instance `yibu-8fcc27f5`, used APK SHA-256
`439f599b55f305482af378ccaa2796ab758c6e56463e7c028f00c4923f3a840b`.
ADB transferred only the 788,510-byte candidate selection with SHA-256
`b90455f0f090f8ff12a69933c22e8c4e2d37f576834d97ad71c4fab9fc7e7a48`.
Before first use, no prefix/runtime existed for this selection; 10 archives were
already cached and the 208,690-byte tray archive had deliberately been evicted.
Normal Steam startup downloaded that missing archive directly on the phone;
all 11 cache hashes and 5,391 installed file hashes then passed. Only private
Steam authentication was restored, not an installed home or prefix.

The desktop-mode Steam launcher reached the signed-in library. An actual Play
click launched Lost Castle PID 624 through native Wayland and DXVK/Mali at
2358x1216. The screen controller selected a new save, confirmed Start and advanced
visible Chinese dialogue; normal window close removed the game. Relaunch was
not accepted: Steam warned that the same account was playing My Little Shark
on another computer. The attempt was cancelled without disconnecting that game;
Steam was exited normally and authentication backed up privately. Cloud sync
also warned and was not accepted. This is download/install and scoped first-run
acceptance, not complete Steam/Big Picture, relaunch or task-stop acceptance.
Evidence remains in the Android checkout's ignored
`build/validation-20261020/runner-candidate-evidence` and adjacent screenshots.
An earlier public-path instance `yibu-9c134919` resolved all 11 fixed releases and
passed file-hash validation, but its Big Picture screen remained black. That
observation is retained under `releases-public-evidence/black-ui`; it is not a
successful Big Picture regression or a diagnosed cause.

## Optional diagnostics

`build.ps1 diagnostics` produces matching Windows exception helpers;
`build.ps1 wine-capture` produces optional Bionic GFXReconstruct tools. These
products are independent of ordinary runtime assembly and are disabled by
default. The rootfs/glibc capture product is separate. Retain capture limits,
exact module identity and an uncaptured control run; initialization records do
not establish rendered frames, successful replay or application compatibility.
