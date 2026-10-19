"""Final Wine assembly recipes; changing these does not change compiler recipes."""
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import sys

from pipeline_cache import digest, inventory, build_references, support_sources


def assemble_support(out, framework, bridge, observer, tray, invoke):
    out.mkdir()
    for name in ('lsteambridge-server', 'aarch64-windows/steam.exe',
                 'aarch64-windows/lsteamclient.dll', 'aarch64-unix/lsteamclient.so',
                 'aarch64-unix/steamclient.so', 'aarch64-unix/steamclient64.so',
                 'i386-windows/lsteamclient.dll', 'x86_64-windows/lsteamclient.dll',
                 'LICENSE.bridge', 'LICENSE.lsteamclient', 'upstream-revision'):
        destination = out / 'steamworks' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bridge / name, destination)
    shutil.copyfile(bridge / 'steamworks-source.tar.gz', out / 'steamworks-source.tar.gz')
    shutil.copyfile(observer / 'windows-accessibility.exe', out / 'windows-accessibility.exe')
    if tray is not None:
        shutil.copyfile(tray / 'windows-tray.exe', out / 'windows-tray.exe')
    invoke('tar', '--exclude=.git', '-czf', out / 'arlinux-support-source.tar.gz',
           'arlinux/components/steamworks', 'arlinux/components/windows-integration/accessibility',
           'arlinux/components/windows-integration/tray', 'arlinux/components/steamworks/build.sh',
           'arlinux/components/windows-integration/build-accessibility.sh',
           'arlinux/components/windows-integration/build-tray.sh', '-C', out, 'steamworks-source.tar.gz')


def assemble_product(out, framework, base, support, invoke):
    out.mkdir()
    runtime = out / 'runtime'
    shutil.copytree(base / 'runtime', runtime)
    (runtime / 'build-state.json').unlink(missing_ok=True)
    helpers = runtime / 'files/lib/arlinux'
    helpers.mkdir(parents=True, exist_ok=True)
    shutil.copytree(support / 'steamworks', helpers / 'steamworks')
    for name in ('windows-accessibility.exe', 'windows-tray.exe'):
        shutil.copyfile(support / name, helpers / name)
    shutil.copyfile(support / 'arlinux-support-source.tar.gz', out / 'arlinux-support-source.tar.gz')
    metadata = json.loads((runtime / 'bionic-runtime.json').read_text())
    metadata['support'] = {'protocol': 1, 'directory': 'files/lib/arlinux'}
    metadata['originalSources']['support'] = dict(asset='arlinux-support-source.tar.gz',
                                                sha256=digest(out / 'arlinux-support-source.tar.gz'))
    metadata['files'] = {p.relative_to(runtime).as_posix(): digest(p)
                         for p in sorted(runtime.rglob('*')) if p.is_file()
                         and p.name != 'bionic-runtime.json'}
    (runtime / 'bionic-runtime.json').write_text(json.dumps(metadata, indent=2)+'\n')
    for source in base.glob('*.tar.gz'):
        shutil.copyfile(source, out / source.name)
    spec = importlib.util.spec_from_file_location('wine_packager', framework / 'arlinux/package-wine-bionic.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(framework / 'arlinux'))
    spec.loader.exec_module(module)
    module.archive_runtime(runtime, out / 'arlinux-wine-bionic.tar.gz')


def cached_support(cache, framework, bridge, observer, tray, invoke):
    return cache.stage('runtime-support', dict(engine=digest(__file__),
        sources=support_sources(framework),
        dependencies={name: cache.records[name] for name in
                      ('steamworks', 'windows-accessibility', 'windows-tray')}),
        lambda out: assemble_support(out, framework, bridge, observer, tray, invoke))


def cached_product(cache, framework, base, support, invoke):
    return cache.stage('wine-product', dict(engine=digest(__file__),
        packager=inventory(framework/'arlinux/package-wine-bionic.py'),
        dependencies={name: cache.records[name] for name in ('wine-bionic', 'runtime-support')}),
        lambda out: assemble_product(out, framework, base, support, invoke))


def build_target(framework, stage, artifacts, rebuild=False):
    """Consume the declared direct artifacts through the normal component cache."""
    from wine_graph import ComponentCache, PLAN
    from pipeline_cache import run
    import os
    root = framework.parent
    cache = ComponentCache(framework/'build/pipeline', rebuild, stage)
    outputs = {}
    expected = PLAN['stages'][stage]['dependencies']
    if set(artifacts) != set(expected):
        raise ValueError('Assembly inputs differ from the component graph')
    for name, relative in artifacts.items():
        path = PurePosixPath(relative)
        if path.is_absolute() or '..' in path.parts or '\\' in relative:
            raise ValueError('Unsafe component output path')
        output = root.joinpath(*path.parts).resolve(strict=True)
        if not output.is_relative_to(framework/'build/pipeline'/name):
            raise ValueError('Component output escapes its pipeline stage')
        record = json.loads((output.parent.parent/'receipt.json').read_text())
        if (output != framework/'build/pipeline'/name/record['inputs']/record['generation']/'output'
                or inventory(output) != record['outputs']
                or build_references(output) != record['references']):
            raise ValueError('Component output differs from its verified receipt: '+name)
        cache.records[name] = record
        outputs[name] = output
    invoke = lambda *args: run(*args, cwd=framework, env=os.environ.copy())
    if stage == 'runtime-support':
        cached_support(cache, framework, outputs['steamworks'], outputs['windows-accessibility'],
                       outputs['windows-tray'], invoke)
    elif stage == 'wine-product':
        cached_product(cache, framework, outputs['wine-bionic'], outputs['runtime-support'], invoke)
    else:
        raise ValueError('Not an artifact-only assembly stage: '+stage)
