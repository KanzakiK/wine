# Bionic Wine integration

- Read BUILD.md for the sole component build and latest release flow.
- Follow giang17/wine as the implementation upstream; integrate its matching Wine release branch in Git instead of replacing DComp files or replaying a private DComp patch series during builds. Keep Android/Bionic adaptations in this fork.
- Keep Wine scheduling, assembly and publishing here; rootfs only downloads the runtime on demand.
- Component source and fixes belong to the corresponding pinned repositories. Each component has an independent workflow_dispatch and repository-owned cache.
- Do not build, modify or ship Steam Proton. Steam games use this Bionic Wine runtime as a custom compatibility tool.
- Validate actual behavior in a fresh instance before release. Keep download/output/source hashes and archive path safety, without parallel feature or DLL presence lists.
- Keep maintained documentation, comments and developer diagnostics in English.
- Maintain local sources with native Windows Git, Python and PowerShell. Do not create WSL checkouts, build directories or validation worktrees. Linux-specific tests and compilation run on GitHub-hosted runners.
