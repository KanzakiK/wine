# Bionic Wine build and release

This fork owns Bionic Wine integration, its component dependency graph,
hosted dispatch, assembly, source archives and the `latest` publisher.
The Linux entry is `./arlinux/build.sh`. Android's `arlinux/build.ps1 wine`
calls the same coordinator; APK builds request only the independent audio product.
Rootfs distributions have no Wine source or build dependency. Their application
launchers download the published runtime on demand.

Local development uses Windows Git, Python and PowerShell exclusively. Linux
compilation and recipe tests run on GitHub-hosted runners; do not create WSL
source, build or verification trees. The ARM64 PE job runs the Wine recipe tests.

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
