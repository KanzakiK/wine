#!/usr/bin/env bash
# Experimental native Wine backend; reuse version-matched Windows PE modules.
set -euo pipefail
if [[ $# != 8 ]]; then
    echo 'Usage: wine-bionic.sh WINE_SOURCE WINE_TOOLS LLVM_MINGW_BIN NDK_ROOT NATIVE_PREFIX FEX_SOURCE PE_RUNTIME OUTPUT' >&2
    exit 2
fi
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_dir="$(realpath "$1")"
tools_dir="$(realpath "$2")"
mingw="$(realpath "$3")"
ndk="$(realpath "$4")/toolchains/llvm/prebuilt/linux-x86_64"
prefix="$(realpath "$5")"
tls="$(realpath "${BIONIC_TLS_PREFIX:-$prefix}")"
pulse="$(realpath "${BIONIC_PULSE_PREFIX:-$prefix}")"
graphics="$(realpath "${BIONIC_GRAPHICS_PREFIX:-$prefix}")"
vulkan_driver="${BIONIC_VULKAN_DRIVER:-system}"
case "${BIONIC_OPENGL:-zink}" in
    zink) opengl_arg=--with-opengl ;;
    none) opengl_arg=--without-opengl ;;
    *) echo 'Unknown BIONIC_OPENGL.' >&2; exit 2 ;;
esac
vulkan_args=(--vulkan-driver "$vulkan_driver")
if [[ -n "${BIONIC_ARCHIVE:-}" ]]; then
    vulkan_args+=(--archive "$(realpath -m "$BIONIC_ARCHIVE")")
fi
if [[ -n "${BIONIC_DXVK_RUNTIME:-}" ]]; then
    vulkan_args+=(--dxvk-runtime "$BIONIC_DXVK_RUNTIME")
fi
if [[ "$vulkan_driver" == system ]]; then
    vulkan_args+=(--system-vulkan-adapter "$BIONIC_SYSTEM_VULKAN_ADAPTER")
fi
fex_source="$(realpath "$6")"
pe_runtime="$(realpath "$7")"
output="$(realpath -m "$8")"
[[ ! -e "$output" ]] || { echo 'Output already exists.' >&2; exit 2; }
mkdir -p "$repo/build/wine-bionic"
stage="$(mktemp -d "$repo/build/wine-bionic/build.XXXXXXXX")"
echo "Build directory: $stage"
mkdir "$stage/core" "$stage/fex"
mkdir "$stage/source"
# The integration now lives in this Wine checkout. Copy only tracked source:
# walking the checkout would recursively copy build/ into its own destination.
git -C "$source_dir" archive HEAD | tar -xf - -C "$stage/source"
source_dir="$stage/source"
python3 "$repo/arlinux/build/refresh-wine-vkd3d.py" "$source_dir"
bash "$repo/arlinux/build/prepare-wine-dcomp.sh" "$source_dir"
if ! grep -q '/apex/com.android.conscrypt/cacerts' "$source_dir/dlls/crypt32/unixlib.c"; then
    patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-certificates.patch"
fi
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-dwrite-bitmap-cache.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-keyboard-layout.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-dwrite-transformed-hinting.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-pulse.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-utf8-locale.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-shared-storage-security.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-arm64-apc-context.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-local-focus.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-dragdrop-owner.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-wow64-images.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-ahb-mapping.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-opengl-unavailable.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-layered-alpha.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-transparent-initial.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-layered-minimize.patch"
cp "$repo/arlinux/components/windows-integration/tray/protocol.h" "$source_dir/programs/explorer/arlinux_tray.h"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-tray-task.patch"
patch -d "$source_dir" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/wine-bionic-mmap-probe.patch"
(cd "$source_dir/dlls/winevulkan" && python3 make_vulkan)
cp "$fex_source/Source/Windows/UnixLib/"{FEXUnixLib.cpp,FEXUnixLib.h} "$stage/fex/"
patch -d "$stage/fex" -p1 --batch --fuzz=0 < "$repo/arlinux/patches/fex-bionic-unixlib.patch"
export PATH="$mingw:$PATH"
export CC="ccache $ndk/bin/aarch64-linux-android29-clang" CXX="ccache $ndk/bin/aarch64-linux-android29-clang++"
export AR="$ndk/bin/llvm-ar" RANLIB="$ndk/bin/llvm-ranlib"
export CCACHE_BASEDIR="$stage"
# Keep debug/source paths stable across content-addressed build generations.
# Otherwise a new temporary directory defeats caching unchanged source files.
export CFLAGS="-O2 -g -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES -ffile-prefix-map=$stage=/usr/src/arlinux/wine-bionic -fdebug-prefix-map=$stage=/usr/src/arlinux/wine-bionic"
export CPPFLAGS="-I$prefix/include -I$graphics/include" LDFLAGS="-L$prefix/lib -L$graphics/lib -Wl,-z,max-page-size=16384"
export WAYLAND_CLIENT_CFLAGS="-I$prefix/include" WAYLAND_CLIENT_LIBS="-L$prefix/lib -lwayland-client"
export WAYLAND_EGL_CFLAGS="-I$prefix/include" WAYLAND_EGL_LIBS="-L$prefix/lib -lwayland-egl"
export XKBCOMMON_CFLAGS="-I$prefix/include" XKBCOMMON_LIBS="-L$prefix/lib -lxkbcommon"
export XKBREGISTRY_CFLAGS="-I$prefix/include" XKBREGISTRY_LIBS="-L$prefix/lib -lxkbregistry"
export EGL_CFLAGS="-I$graphics/include" EGL_LIBS="-L$graphics/lib -lEGL"
export FREETYPE_CFLAGS="-I$prefix/include/freetype2" FREETYPE_LIBS="-L$prefix/lib -lfreetype"
export FONTCONFIG_CFLAGS="-I$prefix/include" FONTCONFIG_LIBS="-L$prefix/lib -lfontconfig"
export GNUTLS_CFLAGS="-I$tls/include" GNUTLS_LIBS="-L$tls/lib -lgnutls"
export PULSE_CFLAGS="-I$pulse/include" PULSE_LIBS="-L$pulse/lib -Wl,-rpath-link,$pulse/lib/pulseaudio -lpulse"
# configure requires a Gradle executable even with wineandroid.drv disabled.
export PKG_CONFIG_LIBDIR=/nonexistent GRADLE=/bin/true
(
    cd "$stage/core"
    "$source_dir/configure" --host=aarch64-linux-android --enable-wineandroid_drv=no \
        --enable-win64 --enable-archs=arm64ec,aarch64,i386,x86_64 --with-wine-tools="$tools_dir" \
        --disable-tests --without-x --without-xinput --without-xinput2 --with-freetype --with-fontconfig --without-xshm \
        --with-wayland --disable-winex11.drv --without-unwind --with-gnutls --without-gstreamer \
        --without-alsa --with-pulse --without-dbus "$opengl_arg" --with-vulkan \
        --prefix=/arlinux-wine --exec-prefix=/arlinux-wine
) > "$stage/configure.log" 2>&1
if [[ "$opengl_arg" == --with-opengl ]]; then
    grep -q '^#define SONAME_LIBEGL ' "$stage/core/include/config.h" || {
        echo 'Wine could not enable Wayland EGL; check the Bionic graphics prefix.' >&2; exit 2;
    }
fi
grep -q '^#define SONAME_LIBVULKAN ' "$stage/core/include/config.h" || {
    echo 'Wine could not enable Vulkan; check the Bionic graphics prefix.' >&2; exit 2;
}
(
    cd "$stage/core"
    mapfile -t modules < <(sed -n -E 's/^(dlls\/[^ :]*\.so):.*/\1/p' Makefile)
    make -j"${JOBS:-8}" loader/wine server/wineserver "${modules[@]}"
    # winebus PE and Unix halves exchange private structures. Build the driver
    # from this same prepared source instead of reusing a potentially older PE.
    make -j"${JOBS:-8}" dlls/winebus.sys/{aarch64,i386,x86_64}-windows/winebus.sys
    make -j"${JOBS:-8}" programs/explorer/{aarch64,i386,x86_64}-windows/explorer.exe
) > "$stage/build.log" 2>&1
ccache "$ndk/bin/aarch64-linux-android29-clang++" -std=c++17 -fPIC -O2 \
    "-ffile-prefix-map=$stage=/usr/src/arlinux/wine-bionic" \
    -c "$stage/fex/FEXUnixLib.cpp" -o "$stage/fex/FEXUnixLib.o"
"$ndk/bin/aarch64-linux-android29-clang++" -shared -static-libstdc++ -Wl,-z,defs \
    -Wl,-z,max-page-size=16384 "$stage/fex/FEXUnixLib.o" -o "$stage/fex/libarm64ecfex.so"
cp "$stage/fex/libarm64ecfex.so" "$stage/fex/libwow64fex.so"
tar -czf "$stage/wine-source.tar.gz" -C "$stage" source
python3 "$repo/arlinux/package-wine-bionic.py" --core "$stage/core" --fex "$stage/fex" \
    --native-prefix "$prefix" --dependency-prefix "$tls" --dependency-prefix "$pulse" \
    --graphics-prefix "$graphics" --ndk "$ndk" --pe-runtime "$pe_runtime" --output "$output" \
    --wine-source-archive "$stage/wine-source.tar.gz" \
    "${vulkan_args[@]}"
# Local build metadata is written after archive creation; private source/build
# paths never enter the redistributable runtime archive.
python3 - "$stage" "$output" <<'BUILD_STATE'
import json, sys
from pathlib import Path
stage, output = map(Path, sys.argv[1:])
(output/'build-state.json').write_text(json.dumps({'source': str(stage/'source'), 'core': str(stage/'core')}) + '\n')
BUILD_STATE
echo "Built experimental Bionic runtime: $output"
