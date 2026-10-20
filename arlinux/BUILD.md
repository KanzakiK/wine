# Bionic Wine build and release

This Wine fork owns Bionic Wine integration, the component dependency graph,
source archives, hosted dispatch and public runtime selection. Rootfs products
only download the runtime on demand. They neither build nor dispatch Wine.

The workstation entry is the Android repository's `build.ps1`; follow its
[canonical entry guide](https://github.com/taowen/arlinux/blob/main/docs/BUILD.md).
`arlinux/build.sh` and `arlinux/build/` are the implementation used by that entry
and the independent component runners. Do not create another workstation builder,
use WSL, assemble an old runtime archive, or bypass the pinned graph stages.

## Independent runtime producers

Each producer owns its compiler workflow, runtime manifest, archives and release.
There is no `wine-product` stage, total runtime manifest, version combination
selection or product-wide compatibility hash. `build/github-components.json` is
the sole compiler dependency graph; it is not an installed version lock.

The producers are `wine-bionic`, `wine-pe-aarch64`, `wine-pe-x86_64`,
`wine-pe-i386`, `fex`, `dxvk`, `windows-fonts`, `wine-addons`, `steamworks`,
`windows-accessibility` and `windows-tray`. Their independently hashed compiler
receipts and source archives remain reproducible. Compiler dependencies are
built only when required by the requested producer; building `wine-bionic`
does not wait for Steamworks or the x86 PE producers.

The phone caches each producer's extracted files independently. Updating one
producer downloads and extracts only its changed archives. Immutable launch
views retain real files from the native producer for Wine's realpath-based data
lookup and use relative symbolic links for other producers. Running processes
keep their old view.
The view's `bionic-runtime.json` contains merged runtime configuration and file
ownership, not a producer-version vector or a requirement to rebuild the other
producers. Steam and Windows launcher apps share these files and the instance's
single Wine prefix. Conflicting file ownership and unsafe archives still fail.

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

Use the Android checkout's sole entry. A Wine invocation defaults to the native
`wine-bionic` producer. Select any other producer explicitly:

```powershell
.\build.ps1 wine -WineRef FULL_PUSHED_COMMIT -WineComponent wine-bionic
.\build.ps1 wine -WineRef FULL_PUSHED_COMMIT -WineComponent wine-pe-aarch64
```

The command prints the exact producer directory. Each directory contains its
own `arlinux-PRODUCER.json`, `github-component.json` and verified download receipt.
It never generates an aggregate runtime selection.

Before acceptance, replace the tested instance through the Android guide's
canonical rootfs deploy/import flow. Debug APKs do not embed rootfs. Confirm the
device serial, package and explicit instance ID; preserve only Steam test
credentials using the documented exception. Never restore old homes, installed
applications or Wine prefixes. Keep the instance-external verified download cache.

With that fresh instance and desktop stopped, deploy the one changed producer:

```powershell
.\build.ps1 wine -WineRef FULL_PUSHED_COMMIT -WineComponent wine-bionic -Serial SERIAL -Instance yibu-FRESH_INSTANCE
```

Only the small verified producer manifest crosses ADB. Its override is stored at
`instances/INSTANCE/home/.config/arlinux/wine-components/PRODUCER.json`.
The phone downloads archives directly through the usual routing/cache/checksum
path. Other producers keep their own independent public releases. Missing
candidate metadata fails rather than silently falling back. Subsequent Wine-only
changes require no APK rebuild or latest publication. A protocol change requires
a new APK and fresh distribution through the same canonical entry.

Complete install, interaction, close, reopen and task stop on the device. Retain
APK/source hashes, per-producer receipts, process maps, screenshots and logs in
private validation evidence. Debug receiver maintenance and authentication
commands are maintained only in the [Android diagnostic guide](https://github.com/taowen/arlinux/blob/main/tools/diagnostics/README.md#debug-yibu-instance-maintenance).
Release builds expose no candidate receiver. Do not treat compilation as device
acceptance. Preserve the tray as an independent window selected in Yibu's bar.

## Publishing fixed component releases

Every producer publishes `runtime.tar.gz` in its own fixed
`arlinux-PRODUCER-latest` release. GitHub supplies its SHA-256, size and URL.
There is no public or internal total-version JSON and no pairing token.
The rootfs owns only stable endpoint names in `windows-downloads.tsv`, never a
Wine build dependency or a version combination.

Prepare a delivery candidate from one exact verified producer manifest:

```powershell
$wineRef = 'FULL_PUBLISHER_COMMIT'
$manifest = 'EXACT_PRODUCER_DIRECTORY/arlinux-wine-bionic.json'
.\build.ps1 publish-wine -WineRef $wineRef -Archive $manifest -Check -Serial SERIAL -Instance yibu-FRESH_INSTANCE
```

This dispatches only that producer's release job. The runner verifies declared
runtime/source hashes and retains a deterministic immutable candidate archive;
it does not compile Wine or restore compiler caches. Windows handles only the
small `public-release/candidate.json` descriptor and receipts. The phone tests
the candidate archive directly. Finish the fresh-instance journey before promotion.

```powershell
.\build.ps1 publish-wine -WineRef $wineRef -Archive $manifest
```

Promotion copies the exact tested archive to that producer's fixed release
without rebuilding or repackaging. Other producers are untouched. Compare the
published SHA-256 with the tested archive, then use a fresh instance without
candidate overrides to verify the ordinary public download path. Publishing one
component never waits for unrelated component publications.

## Optional diagnostics

`build.ps1 diagnostics` produces matching Windows exception helpers;
`build.ps1 wine-capture` produces optional Bionic GFXReconstruct tools. These
products are independent of ordinary runtime assembly and are disabled by
default. The rootfs/glibc capture product is separate. Retain capture limits,
exact module identity and an uncaptured control run; initialization records do
not establish rendered frames, successful replay or application compatibility.
