#!/usr/bin/env bash
# Build both Wine CPU modules and their Unix helpers from one pinned FEX source.
set -euo pipefail
if [[ $# != 2 ]]; then
    echo 'Usage: fex-windows.sh LLVM_MINGW_BIN OUTPUT_DIRECTORY' >&2
    exit 2
fi
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source="$repo/arlinux/components/FEX"
output="$(realpath -m "$2")"
export PATH="$(realpath "$1"):$PATH"
mkdir -p "$output"
for entry in arm64ec:arm64ecfex aarch64:wow64fex; do
    triple="${entry%%:*}"
    module="${entry##*:}"
cmake -G Ninja -S "$source" -B "$output/$triple" \
    -DCMAKE_TOOLCHAIN_FILE="$source/Data/CMake/toolchain_mingw.cmake" \
    -DMINGW_TRIPLE="$triple-w64-mingw32" -DCMAKE_BUILD_TYPE=Release \
    -DENABLE_FEXCORE_PROFILER=True -DENABLE_LTO=False -DBUILD_TESTING=False \
    -DTUNE_CPU=none -DRANGES_NATIVE=OFF -DBUILD_STEAM_SUPPORT=True \
    -DENABLE_VIXL_DISASSEMBLER=OFF -DENABLE_ZYDIS=OFF
cmake --build "$output/$triple" --target "$module" -j"${JOBS:-8}"
install -m755 "$output/$triple/Bin/lib$module.dll" "$output/lib$module.dll"
done

git -C "$source" rev-parse HEAD > "$output/source-commit"
tar -czf "$output/fex-source.tar.gz" --exclude=.git -C "$repo/arlinux/components" FEX
sha256sum "$output/"lib*fex.dll "$output/fex-source.tar.gz"
