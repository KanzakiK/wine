"""Content identities and bootstrap requirements for the Wine component graph."""
import hashlib
import json
from pathlib import Path
import subprocess

PE = ('arlinux/build/wine-pe.sh', 'arlinux/build/refresh-wine-vkd3d.py',
      'arlinux/build/prepare-wine-dcomp.sh', 'arlinux/patches',
      'arlinux/components/windows-integration')
SOURCES = {
    'bionic-deps': ('arlinux/components/bionic-deps', 'tools/build', 'toolchain.json'),
    'bionic-x11': ('arlinux/build/bionic-x11.sh', 'arlinux/components/libX11'),
    'wine-pulse': ('arlinux/components/pulseaudio-android', 'tools/build/ndk-env.sh', 'toolchain.json'),
    **{'wine-pe-'+arch: ('@wine', *PE) for arch in ('aarch64', 'x86_64', 'i386')},
    'wine-pe': (),
    'fex': ('arlinux/build/fex-windows.sh', 'arlinux/components/FEX'),
    'dxvk': ('arlinux/build/dxvk-windows.sh', 'arlinux/patches/dxvk-optional-pipeline-library.patch'),
    'wine-pe-package': ('arlinux/package-wine-pe.py', 'arlinux/wine_pe_debug.py'),
    'wine-tls': ('arlinux/components/bionic-deps',),
    'wine-graphics': ('arlinux/build/wine-bionic-graphics.sh', 'arlinux/components/mesa',
                      'arlinux/components/libxshmfence', 'arlinux/components/libhybris'),
    'wine-vulkan': ('arlinux/components/libhybris', 'arlinux/components/android-headers', 'arlinux/patches'),
    'wine-bionic-compile': ('@wine', *PE, 'arlinux/build/wine-bionic.sh', 'arlinux/components/FEX'),
    'wine-bionic': ('arlinux/package-wine-bionic.py', 'arlinux/wine_pe_debug.py',
                    'arlinux/wine_fonts.py', 'dlls/winebus.sys/bus_arlinux.h', 'arlinux/winebus', 'COPYING.LIB'),
    'steamworks': ('arlinux/components/steamworks',),
    'windows-accessibility': ('arlinux/components/windows-integration',),
    'windows-tray': ('arlinux/components/windows-integration',),
    'wine-diagnostics': ('arlinux/build/windows-debug.sh', 'arlinux/windows-debug.py',
                         'arlinux/components/windows-integration'),
    'runtime-support': ('arlinux/components/steamworks', 'arlinux/components/windows-integration',
                        'arlinux/build/runtime_assembly.py'),
    'wine-product': ('arlinux/package-wine-bionic.py', 'arlinux/build/runtime_assembly.py'),
    'wine-capture': ('arlinux/components/gfxreconstruct',),
    'windows-fonts': (),
}
RESOURCES = {name: ('mingw',) for name in SOURCES}
for name in ('bionic-deps', 'bionic-x11', 'wine-pulse', 'wine-tls', 'wine-graphics', 'wine-vulkan'):
    RESOURCES[name] = ('ndk',)
RESOURCES.update({'wine-pe-package': ('addons',), 'wine-bionic-compile': ('mingw', 'ndk'), 'wine-bionic': ('ndk',),
                  'runtime-support': (), 'wine-product': (), 'wine-capture': ('ndk',), 'windows-fonts': ()})
SHARED = ('arlinux/build/component_inputs.py', 'arlinux/build/github-component.py',
          'arlinux/build/wine-pipeline.py', 'arlinux/build/pipeline_cache.py',
          'arlinux/build/wine_graph.py', 'arlinux/build.sh')


def core_path(name):
    return not (name.startswith(('arlinux/', '.github/', 'tools/build/')) or
                name in ('.gitmodules', 'toolchain.json'))


def tree_entries(repo, revision, paths=()):
    args = ['git', '-C', str(repo), 'ls-tree', '-r', '-z', revision]
    if paths:
        args += ['--', *paths]
    entries = {}
    for record in subprocess.check_output(args).split(b'\0'):
        if record:
            metadata, name = record.split(b'\t', 1)
            entries[name.decode()] = metadata.decode()
    return entries


def source_inputs(repo, revision, stage, plan):
    paths = SOURCES[stage]
    selected = tree_entries(repo, revision, (*SHARED, *(p for p in paths if p != '@wine')))
    if '@wine' in paths:
        selected.update({n: v for n, v in tree_entries(repo, revision).items() if core_path(n)})
    lock = subprocess.check_output(['git', '-C', str(repo), 'show', revision+':arlinux/build/github-inputs.json'])
    versions = json.loads(lock)
    return dict(sourceSha256=hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest(),
                tools={n: versions[n] for n in RESOURCES[stage]},
                runner=plan['stages'][stage]['runner'],
                artifactInputsOnly=plan['stages'][stage].get('artifactInputsOnly', False))


def request_identity(data):
    fields = {k: v for k, v in data.items() if k not in ('identity', 'cacheSeed')}
    if data.get('format') == 2:
        fields.pop('framework')  # Provenance is retained, but unrelated commits are not build inputs.
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def requirements(stage, plan):
    stages = set()
    def visit(name):
        if name not in stages:
            stages.add(name)
            if not plan['stages'][name].get('artifactInputsOnly'):
                for dependency in plan['stages'][name]['dependencies']:
                    visit(dependency)
    visit(stage)
    paths = {p for name in stages for p in SOURCES[name] if p.startswith('arlinux/components/')}
    modules = sorted({'/'.join(p.split('/')[:3]) for p in paths})
    resources = {r for name in stages for r in RESOURCES[name]}
    return modules, resources
