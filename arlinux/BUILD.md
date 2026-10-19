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
Each component uses an independent workflow_dispatch in its owning repository;
compiler/download caches belong to that repository's standard free runners.
Component requests hash the declared source trees, recipes, toolchain locks and
dependency identities; the producing commit remains provenance, not a blanket
invalidation key. Unrelated integration documentation or FEX changes do not
rebuild PE. Each runner initializes only its dependency closure's source modules
and toolchains. A forced rerun verifies outputs before reusing a published capsule.
Sources are fixed Git submodules. Steamworks owns its committed frontend fixes,
Windows integration owns accessibility/tray, and the audio fork pins its patched
PulseAudio fork. No Steam Proton distribution is built or patched.
Concurrent local coordinators lock each content identity until publication, so
identical requests share one hosted workflow rather than queueing duplicate jobs.
Locks are released by the operating system on process exit. Full commit pins
skip redundant commit-resolution API calls; source and artifact hashes still
determine reuse.
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

Runtime-support assembly still imports transitive compiler and toolchain inputs.
The [current check](https://github.com/taowen/wine/actions/runs/39150836195)
took 354 seconds overall, including a 265-second build step. Further reduction
needs direct artifact contracts and component-specific engine identities before
changing the shared pipeline engine; otherwise an assembly-only change can
invalidate unrelated compiler caches. Keep assembly in the single product graph.

The next optimization recipes remove intermediate PE gzip creation/extraction:
`package-wine-pe.py` produces the declared runtime directory directly; the
component capsule remains responsible for transport compression and verification.
Only `wine-product` creates the downloadable Bionic runtime archive. The native
component exports Steamworks headers and ntdll ABI inputs instead of its complete
object/source work tree. License source archives are retained. x64/i386 PE jobs
export their Windows modules; common data and host tools come from ARM64.

Final support/product assembly implementation lives in `build/runtime_assembly.py`
and is a direct input of those two stages. Subsequent assembly-only edits do not
change the shared compiler engine. Initial migration still changes shared inputs.
These recipe changes require hosted builds and fresh-instance acceptance; they
are not yet measured speedup or compatibility results.

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
./arlinux/build.sh publish-wine build/products/wine/arlinux-wine-bionic.tar.gz --check
./arlinux/build.sh publish-wine build/products/wine/arlinux-wine-bionic.tar.gz
```

Publish only the exact runtime validated on fresh device instances. The publisher
verifies declared file hashes and matching source archives, then updates latest;
it does not rebuild or modify a rootfs checkout. `--manifest` is an optional
consumer-side download pin output. Capsule prereleases are build inputs, not
acceptance results. Missing direct inputs and actual command errors fail builds;
do not add parallel feature/file/version presence lists.

The optional diagnostics product builds the standalone Windows observer and probe on
its own x64 runner and carries the Wine-owned guest capture helper. The Windows
host diagnostic command downloads this product; it never invokes WSL.
