# Bionic Wine build and release

The Wayland IME activation fix adapts Ziia Shi's
[Wine MR10007 v9](https://list.winehq.org/hyperkitty/list/wine-gitlab@list.winehq.org/thread/HHQJWJIYCKDSLTIFASH4CGNZ5TI6PEDK/)
directly in this fork. `ImeSetActiveContext` communicates activation to the
driver; text-input-v3 is enabled only for associated input contexts, rather
than every focused game window. The adaptation preserves current composition
cancellation, uses a consistent text-input/window-data lock order, and removes
an enabled child from its toplevel's count when destroyed. Validate held WASD
with the normal IBus Wayland bridge running, and candidate text input in an
editor. Stopping IBus is only a diagnostic isolation step, never acceptance.

Device validation on 2026-10-19 used Xiaomi 15 (`3fad759`), package
`io.taowen.arlinux.dev`, newly installed instance `yibu-6fe7ad34`, and framework
`b946e9561247a621a8baf823e511655ef81bc803`. The tested runtime archive SHA-256
was `5095b708bad116de4612f34ab437e9c860d8fe90e64cb80c5eb47ff7c4f003c7`.
With normal IBus running, LivingBattle entered 3D gameplay; overlay forward
movement reduced the target distance from 44 to 28 metres, releasing stopped
movement, and left/right/back/diagonal movement worked. WeChat IME candidate
selection entered `你好` in Notepad, confirmed through the existing MSAA observer.
The game exited, but the Steam facade remained alive during observation;
successful game relaunch and complete task cleanup were not verified. These
results establish the input fix, not complete game compatibility or approval
to publish `latest`. Later source commits require their own exact-product
validation. Evidence is retained in the Android checkout under
`build/validation-20261019/steam-launch`, including `wasd-fixed-acceptance`,
`wasd-gameplay-*.png` and `ime-fixed-notepad-msaa.txt`.

The foreign GDI delivery candidate adapts Erhan Bilgili's
[Wine-Wineland transport](https://github.com/nanomatters/wine-wineland/commit/908f7702fbf6e6edb761daa47476d283e52b60f1)
into ordinary fork sources. Wayland opts into shared-memory producer surfaces
when a window DC's top-level belongs to another process, including a locally
owned child. Stable slots remain unavailable until the compositor releases them;
failed or backpressured publication keeps dirty bounds for retry. The consumer
preserves source cropping and producer ordering under the owner window. This
imports the GDI path only; GPU swapchains retain their existing WSI path.
Native and PE builds both regenerate the changed server protocol. This candidate
is pending fresh-instance Power BI and application/game regression; it is not
approval to publish latest.

This fork owns Bionic Wine integration, its component dependency graph,
hosted dispatch, assembly, source archives and the `latest` publisher.
The Linux entry is `./arlinux/build.sh`. Android's `arlinux/build.ps1 wine`
calls the same coordinator; APK builds request only the independent audio product.
Rootfs distributions have no Wine source or build dependency. Their application
launchers download the published runtime on demand.

Local development uses Windows Git, Python and PowerShell exclusively. Linux
compilation runs on GitHub-hosted runners; do not create WSL source, build or
verification trees. Hosted builds compile the actual product; acceptance uses
the complete user journey on fresh device instances. Do not gate ARM64 PE on
mock implementations of other graph stages.

`arlinux/build/github-components.json` is the single Wine component graph.
Compiler components use independent workflow_dispatch in their owning repository;
compiler/download caches belong to that repository's standard free runners.
The final `wine-product` stage executes in the Windows coordinator and only pins
independent producer manifests. Wine core, Steamworks, accessibility and the task
owner publish their own manifests and immutable download archives in their owning
repositories. There is no combined runtime archive or `runtime-support` job.
The coordinator never downloads compiler capsules to assemble this selection.
Ordinary product transfers resolve the pinned manifests and fetch their independent
archives through the content-addressed cache. Runtime acceptance and explicit
latest promotion remain separate; the selection build does not promote latest.

The new selection asset is `arlinux-wine-manifests.json` (format 2), referring to
format-1 producer manifests by immutable URL, SHA-256 and size. The previous
`arlinux-wine-runtime.json` asset remains frozen for earlier launchers. Validate
the new launcher and an exact candidate selection on a fresh instance before
promoting the new asset; publish that selection before releasing its consumer APK.
Updating one producer does not repackage or download the other producers again.
Component requests hash the declared source trees, recipes, toolchain locks and
dependency identities; the producing commit remains provenance, not a blanket
invalidation key. Unrelated integration documentation or FEX changes do not
rebuild PE. Each runner initializes only its dependency closure's source modules
and toolchains. A forced rerun verifies outputs before reusing a published capsule.
Sources are fixed Git submodules. Steamworks owns its committed frontend fixes,
Windows integration owns accessibility/tray, and the audio fork pins its patched
PulseAudio fork. No Steam Proton distribution is built or patched.

Recipe boundaries are declared in `component_inputs.py`. Its declaration tables
contribute their resolved per-stage paths and tool pins, not the entire table's
text. Shared assembly recipes hash the selected Python functions, imports and
module-level initialization; compiler stages do not consume unrelated assembly
functions. Keep component source dependencies declared when adding a recipe.
Both hosted request identities and internal stage receipts use the scoped recipe
inputs. Changes to the common compiler engine still invalidate affected stages.
Final distribution publication and receipt writing live in `runtime_distribution.py`,
so changing that product's packaging does not change the compiler engine.

The coordinator prioritizes the longest remaining dependency chain among ready
tasks. A checksum-bound `component.json` published after all outputs releases
dependents immediately; optional workflow cache saving may finish later. It still
verifies the expected request fields and archive hashes; an incomplete upload
never satisfies the dependency. Workflow-tail failures must be inspected separately
from product validity. The `arlinux-v3-` compiler caches exclude duplicate PE
output/source/tool trees: those are already retained in verified component capsules.
Earlier caches with unchanged path lists may seed the first migration. PE's
reduced path list changes Actions' cache version, so its first migration can be
cold despite legacy restore-key prefixes; subsequent saves contain the compact
payload. This migration changes identities once and requires hosted verification;
do not present the first migration build as steady-state incremental performance.

The first v3 hosted runs produced these compressed cache payloads (bytes from
GitHub's cache API, matched to the exact component request identities):

| PE stage | Representative previous v2 payload | First v3 payload |
|---|---:|---:|
| [ARM64](https://github.com/taowen/wine/actions/runs/39266884035) | 3,099,938,526 | 393,743,578 |
| [x64](https://github.com/taowen/wine/actions/runs/39266900110) | 2,198,182,206 | 193,124,750 |
| [x86](https://github.com/taowen/wine/actions/runs/39266880380) | 2,199,750,003 | 187,674,728 |

ARM64's cache-save step took 11 seconds, compared with 111 seconds in the
previous run 39262239615. This is an observed cache-I/O comparison, not an
end-to-end compiler speedup: the v3 migration had a cold cache and its compiler
cache has not accumulated the same history as v2. Its build step took 838 seconds.
Subsequent warm cache restoration and complete product acceptance remain separate
verification tasks. A later sole-entry invocation at framework c8309fc reused
all three published PE components rather than dispatching new PE jobs; this
checks recipe reuse, not warm compiler performance.

Attempt 2 restored the 393,743,578-byte ARM64 cache in about 3 seconds and
completed its build step in about 124 seconds, but failed the strict repeated-
output check at publication. Do not count it as a successful reproducible build.
Source archives previously retained checkout/generated file mtimes, and exported
host-tool trees included runner-specific configure logs. The follow-up recipes
normalize source archive ordering, ownership and timestamps, and export usable
host tools without diagnostic logs (the private builder retains those logs).
Reproducibility verification of these follow-ups is pending. On a mismatch the
publisher now compares checksum-bound receipts and reports bounded changed paths;
it never replaces a conflicting immutable asset or relaxes output validation.
Transport/publication code also has a separate recipe fingerprint: changing a
capsule publisher can dispatch a new publication without invalidating unchanged
compiler-stage receipts.
FEX is pinned to an unmodified upstream FEX-Emu/FEX commit. The taowen/FEX
fork hosts standalone CI only; do not maintain translator or ARM64EC behavior
patches there. Keep product integration and diagnostic recipes outside FEX.
Concurrent local coordinators lock each content identity until publication, so
identical requests share one hosted workflow rather than queueing duplicate jobs.
Locks are released by the operating system on process exit. Full commit pins
skip redundant commit-resolution API calls; source and artifact hashes still
determine reuse.
The workstation retains the verified immutable component reference beside its
completion manifest. A repeat checks the reference's repository/identity/URL,
the manifest SHA-256 and all requested input fields locally before reuse. Missing
or damaged metadata is resolved again from GitHub. This avoids repeat release-API
lookups without caching mutable latest selections or accepting unverified outputs;
binary downloads and final product receipts retain their separate hash checks.
Each component timing records `manifestSource` (`local` or `github`) so a local
metadata hit cannot be presented as a faster hosted compilation.
Hosted audio validation at framework da7a673 passed in run 39276739956. Its first
coordinator invocation took 193.422 seconds including hosted work and transfer;
the next sole-entry invocation took 0.976 seconds overall, with 0.204 seconds
for its locally verified component manifest and 0.015 seconds for verified product
reuse. The timing recorded `manifestSource: local`. This establishes metadata and
product cache reuse, not a compiler speedup or Wine application acceptance.
After successful publication, workflows remove obsolete pipeline input identities
and generations before saving Actions caches. Current generations and directories
referenced by current receipts remain at their original paths. This bounds cache
growth without relocating compiler tools or discarding live ABI headers.
The cache namespace is `arlinux-v2-`, with old verified entries retained as restore
seeds. This lets compacted entries be saved despite Actions cache immutability.
[The x64 PE verification](https://github.com/taowen/wine/actions/runs/39147024702)
passed twice: 163 and 125 seconds overall, with build steps of 11 and 7 seconds.
The saved cache decreased from 634,982,115 to 367,580,990 bytes; both attempts
verified the same published component. Runner preparation still accounts for
most of the warm job's duration.

PE and assembly jobs skip deletion of unrelated preinstalled runner SDKs;
runtime-support and final-product assembly use the smaller host package group.
The [subsequent x64 PE check](https://github.com/taowen/wine/actions/runs/39148239130/attempts/2)
passed in 107 and 55 seconds, with host preparation taking 18 and 17 seconds
and the build step taking 11 seconds each time.

Capsule imports stream Zstandard into tar extraction, retaining the declared
checksum, path-safety, mode and link handling without a temporary full tar.
Hosted tests exercise repeated extraction of read-only files and hardlinks,
executable modes, internal symlinks, corruption and escaping paths.
When Actions has restored stage receipts, older release seeds cannot overwrite
those output generations. The pipeline still verifies current inputs and output
hashes before reuse; a receipt alone does not authorize a cache hit.

The graph marks support and final-product assembly with `artifactInputsOnly`.
These jobs import and validate only their direct component outputs and receipts;
compiler toolchains and transitive compiler work trees are not assembly inputs.
The support job archives its own sources, so final assembly needs no component
source checkout. Both still use the same assembly recipes and component cache.
Hosted preparation installs the capsule decoder without APT or compiler setup.
The first migration changes shared dispatcher identities; later recipe edits
remain isolated in `runtime_assembly.py`.

Actual hosted builds on 2026-10-19 measured:

| Stage | Previous workflow | Direct-artifact workflow | Build step before / after |
|---|---:|---:|---:|
| [Support](https://github.com/taowen/wine/actions/runs/39196742489) | 232s | 34s | 143s / 3s |
| [Final product](https://github.com/taowen/wine/actions/runs/39196808346) | 565s | 121s | 359s / 55s |

Baselines were runs 39189815033 and 39190172799. Workflow times include
preparation, transfer and publication; they are not complete Wine build times
and vary with runner/network load. Workstation `build-timing-PRODUCT.json`
records component waits, product transfer and total duration. Both timing and
`products-PRODUCT.json` are scoped by requested product, so concurrent audio
and Wine preparation cannot overwrite each other's reports.

The next optimization recipes remove intermediate PE gzip creation/extraction:
`package-wine-pe.py` produces the declared runtime directory directly; the
component capsule remains responsible for transport compression and verification.
Only `wine-product` creates the downloadable Bionic runtime components. The native
component exports Steamworks headers and ntdll ABI inputs instead of its complete
object/source work tree. License source archives are retained. x64/i386 PE jobs
export their Windows modules; common data and host tools come from ARM64.

Final support/product assembly implementation lives in `build/runtime_assembly.py`
and is a direct input of those two stages. Subsequent assembly-only edits do not
change the shared compiler engine. Initial migration still changes shared inputs.
Hosted assembly is measured above; fresh-instance acceptance remains a separate
requirement from those build-time results.

Native compilation is now the `wine-bionic-compile` component. It depends on
ARM64 PE host tools, native dependencies, TLS, Pulse and graphics, without waiting
for x64/i386 PE, FEX/DXVK packaging, fonts or the Vulkan adapter. `wine-bionic`
consumes the compiled payload and completed PE/runtime inputs to assemble the
runtime. Steamworks depends on the compiled ABI and merged PE import libraries,
so it can build alongside runtime assembly. ARM64/ARM64EC cross-linked modules
remain in the same PE job. The compiled payload carries headers and actual
binaries, not compiler objects or references to a private native build tree.
All tasks remain independent dispatches in their owning repositories and are
scheduled by the same product graph. Hosted validation passed for
[native compilation](https://github.com/taowen/wine/actions/runs/39178328531),
[Steamworks](https://github.com/taowen/arlinux-steamworks/actions/runs/39178857778)
and the [final product](https://github.com/taowen/wine/actions/runs/39179797837).
This does not replace fresh-instance device acceptance.

Steamworks native C++ files now invoke ccache directly. Its server and launch
helper compile to cached objects before linking, and intermediate objects are
removed from the exported capsule. The recipe remains in the pinned Steamworks
repository. Its first hosted build passed and recorded 896 cacheable calls;
this populated the cache and does not measure a warm Steamworks rebuild.

Workstation product downloads retain manifests, partial transfers and verified
capsules under the shared `github-state/downloads/COMPONENT_ID` directory, not
a per-invocation temporary directory. Concurrent consumers lock that component.
Missing parts download concurrently (up to four); a restarted transfer resumes
its verified parts. A completed partial file is verified and promoted without
another request. Successful assembly removes
redundant part copies while retaining the verified complete capsule.
The audio product was verified through the sole workstation entry after changing
the integration pin: the first run reused the identical component in 6.5 seconds
and the repeat verified its local output in 2.0 seconds, without binary downloads.
This is not a first-download bandwidth measurement.
Before transferring, the coordinator also finds identical component references
in canonical per-commit product caches, verifies every output hash, and copies
the exact verified files into the new isolated output. An integration pin change
therefore does not require downloading an unchanged product again. Changed
component contents still need their first download. Existing capsules currently
bundle distributables and source archives, so reducing a new candidate's first
transfer further requires separate published download assets.

The actual 992,832,136-byte final capsule was interrupted after 737,935,360
bytes. A second sole-entry invocation resumed at that exact offset and verified
SHA-256 `7bdeeef3079082fd2760447111a9e82ce3472e1896cae1481fd7f99082c06a60`.
Changing to another integration pin with the same final component then completed
in 16.1 seconds by copying verified local outputs, without binary downloads.
The persistent transfer was consumed by the normal product extractor; no
synthetic archive or alternative download command was used.

### Runner transfer and invalidation follow-up (2026-10-20)

The font-fallback build exposed a shared-adapter invalidation: the adapter's
entire Git blob contributed to `sourceSha256`, despite its compiler recipe
having a scoped AST hash. Font/capture/diagnostic handlers now have separate
functions, and each stage fingerprints only its selected handler and common
bootstrap. Publication has a separate fingerprint, so publisher-only changes
still dispatch verification without changing compiler recipe inputs. The
download helper's actual transfer functions are declared inputs as well.
This migration changes identities once; it is not itself a warm-build speedup.

The old vendor cache used one key for the entire tool lock across tasks needing
different resources. Its first writer could save only one tool, while other
tasks restored that immutable partial cache and downloaded the missing tools
again. NDK, MinGW and addons now have independent version-hashed archive caches
and directories. They do not cache a second extracted toolchain copy. Component
imports use the same bounded, resumable, checksum-verified multipart downloader
as workstation products. Final runtime groups compress concurrently on up to
four cores, preserving group order and tar/gzip metadata.

Baseline hosted runs from integration `8057e24`:

| Stage / run | Prepare | Build dispatcher | Publication |
|---|---:|---:|---:|
| Native compile / 39322933771 | 302s | 172s | 10s |
| Runtime assembly / 39324150346 | 80s | 324s | 49s |
| Final product / 39325357855 | 2s | 58s | 43s |

The dispatcher includes dependency download/extraction, tool provisioning and
receipt verification, not just compiler time. Cache restoration in those runs
took only a few seconds. At inspection the Wine repository retained
9,568,047,988 bytes in 39 Actions caches, including superseded v2 PE entries of
3,188,395,602 and 2,282,767,553 bytes; do not attribute that pressure to the
current compact v3 compiler cache. New hosted timings and device acceptance
remain separate from these baseline observations.

Hosted verification at integration `ca30806` passed the complete component
chain, including runtime assembly run 39332303780 and final product run
39333244260. Runtime assembly restored all three independent tool caches
(NDK 774,613,289 bytes, MinGW 83,887,405 bytes, addons 167,194,233 bytes).
Its dispatcher took 254 seconds versus 324 in the baseline; this is an
observed stage comparison, not a controlled whole-graph speedup. Native host
preparation took 162 seconds versus 302; network/runner variation also matters.
One coordinator invocation exhausted its GitHub API EOF retries. Re-entering
the sole build command reused the completed components without recompilation.
The subsequent warm audio coordinator completed in 0.421 seconds with zero
product-transfer time. These are build/cache results, not fresh-device approval
of a newly packaged runtime or permission to promote latest.

The runtime assembly log also exposed an Actions prefix collision:
`arlinux-v3-X64-wine-bionic-` restored the `wine-bionic-compile` cache. PE merge
could similarly restore an architecture compiler cache. Pure merge/package/
runtime assembly jobs now skip the irrelevant compiler cache entirely. New
v4 keys delimit stage names with `--`; remaining compiler jobs may use v3/v2
as migration seeds. The key-only wrapper update does not alter product input
identities or rebuild outputs. DXVK run 39334026482 saved the first observed
v4 cache (57,071,146 bytes); PE package run 39335034205 skipped the compiler
cache while restoring MinGW/addons. This establishes the new key and assembly
behavior, not a warm v4 compiler timing.

Two further transfer defects were confirmed during this follow-up:

- Pure assemblers imported an old runtime capsule and its parents as a release
  seed even though they had no compiler work to reuse. The coordinator no longer
  requests seeds for PE merge/package, runtime/support and final assembly.
  Verified runtime record `5752dc93` (run 39335786746) has no `cacheSeed`.
- Unchanged FEX/DXVK links embedded wall-clock timestamps. Their Wine-owned
  recipes now pass `--no-insert-timestamp`; FEX upstream source is unchanged.
  FEX's existing static/alignment options and DXVK's ARM64X option are retained.
  DXVK includes the link policy in its build-directory identity so an existing
  cross file cannot silently retain the old flags.

In the final product, both FEX DLLs differ from the preceding build only in the
eight bytes of their PE/debug timestamps; both header timestamps are now zero.
All 15 DXVK DLL header timestamps are zero as well. DXVK also changed its source/
build-cache directory in this migration and several binaries changed beyond
timestamps; complete repeated-build byte reproducibility is not established.
Do not equate removal of this confirmed timestamp cause with all possible
reproducibility defects being solved.

Concurrent final-product jobs also raced when uploading identical shared
objects: run 39336555736 failed after another job uploaded the same integration
archive at 22:41:33 UTC, between inventory and upload. The publisher now re-reads
the release after an upload failure and reuses the asset only when both GitHub
SHA-256 and byte count match. It never clobbers a conflicting asset.

Final build verification used integration
`47fe73d1dc2bad3825813d81c42ac1d53e402f51`, successful product run 39337031482,
and runtime manifest SHA-256
`35ab8527496a954f00d59f4513e1fbf46de5d120cbc842cb910816f8c28def2d`.
The complete sole-entry warm invocation took 4.93 seconds, verifying all 20
component references and the local product without hosted jobs or binary
downloads. The coordinator itself took 4.094 seconds. Unchanged common data,
fonts and configuration from the previous accepted product reused about
374 MB of objects; source archives remain on-demand publication inputs.
Two obsolete v2 compiler caches and six misclassified PE-merge caches were
removed (about 7.49 GB compressed, regenerable). Current compiler seeds,
immutable releases and user/device data were retained. Public latest was not
promoted, and this newly packaged runtime has not had fresh-device acceptance.

All three incremental PE builds passed with actual compiler invocations:

| Architecture | Cache population build step | Incremental build step | Added ccache hits | Added misses |
|---|---:|---:|---:|---:|
| [ARM64](https://github.com/taowen/wine/actions/runs/39177298054) | 1,285s | 96s | 9,532 | 0 |
| [x64](https://github.com/taowen/wine/actions/runs/39177384110) | 676s | 66s | 4,714 | 0 |
| [x86](https://github.com/taowen/wine/actions/runs/39177295805) | 535s | 55s | 4,931 | 0 |

Population runs were [ARM64](https://github.com/taowen/wine/actions/runs/39174752101),
[x64](https://github.com/taowen/wine/actions/runs/39174846810) and
[x86](https://github.com/taowen/wine/actions/runs/39174752412).
Counters are cumulative in the restored cache; the table uses differences
between the two jobs rather than presenting the cumulative hit percentage as
this invocation's hit rate. These are build-step measurements, not end-to-end
runtime or device acceptance. Changed Wine files still require compilation.

From a clean clone of the intended pushed commit, with Python, zstandard and gh:

```sh
python arlinux/build/install-github-workflows.py
./arlinux/build.sh github --framework-ref COMMIT --product wine --output build/products
./arlinux/build.sh github --framework-ref COMMIT --product audio --output build/products
./arlinux/build.sh github --framework-ref COMMIT --product diagnostics --output build/products
./arlinux/build.sh publish-wine build/products/wine/arlinux-wine-runtime.json --check
./arlinux/build.sh publish-wine build/products/wine/arlinux-wine-runtime.json
```

## Publishing the public latest runtime

Publishing `latest` makes the runtime available to ordinary ARLinux users. Both
the Windows launcher and Steam's Bionic compatibility tool resolve the
`arlinux-wine-runtime.json` asset in
[taowen/wine's latest release](https://github.com/taowen/wine/releases/tag/latest).
This is a public promotion, not a private device deployment or merely a successful
runner build. Existing instances cache a successful release lookup for up to one
hour; an already running Windows application is not replaced during execution.

Use the Android checkout's sole Windows entry, with the full pushed Wine
integration commit and the exact component manifest path reported by that build:

```powershell
.\build.ps1 wine -WineRef COMMIT -Serial SERIAL -Instance INSTANCE
.\build.ps1 publish-wine -WineRef COMMIT -Archive EXACT_TESTED_ARCHIVE -Check
.\build.ps1 publish-wine -WineRef COMMIT -Archive EXACT_TESTED_ARCHIVE
```

The first command builds or verifies the product and explicitly selects that
candidate for one stopped Debug instance. It does not publish `latest`. Before
either publish command, complete the fresh-instance user journey using the
matching APK and this candidate: install, normal Steam/Windows startup, real
interaction, close, restart and end the task. Retain device/package/instance,
APK SHA-256, Wine integration/component/archive identities, actual loaded
runtime evidence, screenshots and logs. Pair APK changes to host/helper interfaces
with their corresponding Wine product; a previously tested older candidate is
not evidence for the new pair. Do not publish a candidate whose required journey
has not passed.

`-Check` verifies the component manifest, archives, declared file hashes and
matching Wine/FEX/DXVK/support sources without changing the public release.
Sources are downloaded on demand for this promotion step, not ordinary device
testing. The final command preserves the immutable Wine source release and replaces
only the new latest JSON manifest with the exact tested bytes. It does not rebuild,
repack, or modify a rootfs. It verifies GitHub's uploaded asset digest and size;
retain that result and compare it with the accepted local archive SHA-256.
The publisher's optional `--manifest` output is a consumer pin, not another build.

The legacy `latest/arlinux-wine-bionic.tar.gz` stays frozen for old APKs. New
builds neither generate it nor publish a compatibility bundle. Runtime groups
(native Wine, each PE architecture, FEX, DXVK, fonts, integration and common data)
are deterministic archives named by SHA-256 in the immutable
`arlinux-wine-components` release. Sources are separate content-addressed assets.
The small latest manifest binds every component URL, size and hash and carries
the runtime metadata. The workstation and guest reuse verified compressed objects
across integration versions; first installation still downloads all runtime
components. Runtime trees are assembled and validated before atomic selection.
The shared download cache is outside instances; it contains no Wine prefix.
This format's runner and fresh-instance device acceptance are pending.

After promotion, remove the Debug candidate selection through the documented
instance maintenance flow and validate the ordinary latest download in another
fresh instance. Confirm its selected/loaded SHA-256 matches the published asset,
then repeat the real launch/interaction/exit journey. Keep private Steam
authentication preparation outside the instance as documented by Android
diagnostics; never restore an old prefix to validate a release.

Keep one selected runtime for ordinary use. Before cleaning device runtime or
workstation product caches, stop their users and check instance candidate records,
the shared current selection, process maps and retained build receipts. Remove
only unreferenced disposable candidates. Do not remove an active archive, compiler
cache, reproducibility sources, or GitHub component capsule prereleases needed by
the dependency graph. Capsule prereleases are build inputs, not competing public
runtime releases. Historical releases are separate from local cache cleanup.

The optional diagnostics product builds the standalone Windows observer and probe on
its own x64 runner and carries the Wine-owned guest capture helper. The Windows
host diagnostic command downloads this product; it never invokes WSL.

## Pending asynchronous DComp readback validation (2026-10-19)

A Xiaomi 15 Power BI/WebView2 diagnostic launch with the ordinary D3D11 backend
reported GPU composition and DirectComposition enabled. Its GPU watchdog then
terminated stalled GPU processes. Temporarily disabling only that watchdog for
stack collection retained the blocked process; this is not a shipping option.
CDP SystemInfo.getProcessInfo identified Wine GPU PID 0x290, avoiding guesses
from child ordering or Android PIDs. WineDbg captured the renderer thread in
DXVK RecursiveSpinlock::lock (d3d11 RVA 0x1d7fc0). The lock at 0xa56d3c was
owned by Wine TID 0x67c. That thread's stack contained DComp readback followed
by D3D11ImmediateContext::MapImage/WaitForResource and a resource wait.
The proposed generic change submits one staging copy, flushes it, polls Map
with D3D11_MAP_FLAG_DO_NOT_WAIT, and keeps the previous pixels while busy.
Pending state follows the retained texture cache and resets on resize.
Fresh-instance application and game acceptance is still pending. Do not
publish latest based on this diagnostic or a successful build alone.
Evidence: Android checkout build/validation-20261019/mouse-game/
pbi-gpu-real-stacks.txt, pbi-gpu-locks.txt, webview-watchdog-native-stack.txt.

## Optional Bionic Vulkan capture

Build the separate diagnostic product from the Android checkout:

```powershell
.\build.ps1 wine-capture -WineRef FULL_PUSHED_WINE_COMMIT
```

The Wine component graph dispatches `wine-capture` independently in
`taowen/gfxreconstruct` on an x64 GitHub runner, using the pinned NDK and Bionic
Wayland headers. Its cache is owned by that repository. This is separate from
the rootfs/glibc `capture` product and is not a dependency of normal Wine builds.
The result is `wine-capture/arlinux-wine-capture.tar.gz` with a SHA-256 receipt;
its internal provenance records the GFXReconstruct commit and per-file hashes.
The ARM64 Bionic capture layer and conversion/info tools use process environment
settings, avoiding Android-wide capture properties. Keep normal graphics layers
and ICD selection intact when opting one owned application job into capture.
Xiaomi 15 fresh-instance diagnostics on 2026-10-20 verified the Bionic layer
loading, bounded initialization capture, conversion to 3,415 parseable JSONL
records and owned-task cleanup with integration `dbaabe6784bd6192e45e466b324f38a89ce2b53a`.
The subsequent uncaptured task had neither the layer nor capture environment.
The captured stream contains no queue submit/present; rendered frames and
faithful replay remain unverified. This is diagnostic-tool validation, not
Power BI or Steam gameplay acceptance. Exact device/APK/runtime evidence is
recorded in the Android diagnostic notes.
