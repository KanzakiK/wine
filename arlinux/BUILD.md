# Bionic Wine build and release

This fork owns Bionic Wine integration, its component dependency graph,
hosted dispatch, assembly, source archives and the `latest` publisher.
The Linux entry is `./arlinux/build.sh`. Android's `arlinux/build.ps1 wine`
calls the same coordinator; APK builds request only the independent audio product.
Rootfs distributions have no Wine source or build dependency. Their application
launchers download the published runtime on demand.

`arlinux/build/github-components.json` is the single Wine component graph.
Each component uses an independent workflow_dispatch in its owning repository;
compiler/download caches belong to that repository's standard free runners.
Sources are fixed Git submodules. Steamworks owns its committed frontend fixes,
Windows integration owns accessibility/tray, and the audio fork pins its patched
PulseAudio fork. No Steam Proton distribution is built or patched.

From a clean clone of the intended pushed commit, with Python, zstandard and gh:

```sh
python arlinux/build/install-github-workflows.py
./arlinux/build.sh github --framework-ref COMMIT --product wine --output build/products
./arlinux/build.sh github --framework-ref COMMIT --product audio --output build/products
./arlinux/build.sh publish-wine build/products/wine/arlinux-wine-bionic.tar.gz --check
./arlinux/build.sh publish-wine build/products/wine/arlinux-wine-bionic.tar.gz
```

Publish only the exact runtime validated on fresh device instances. The publisher
verifies declared file hashes and matching source archives, then updates latest;
it does not rebuild or modify a rootfs checkout. `--manifest` is an optional
consumer-side download pin output. Capsule prereleases are build inputs, not
acceptance results. Missing direct inputs and actual command errors fail builds;
do not add parallel feature/file/version presence lists.
