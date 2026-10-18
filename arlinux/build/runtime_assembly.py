"""Final Wine assembly recipes; changing these does not change compiler recipes."""
import importlib.util
import json
import shutil
import sys

from pipeline_cache import digest


def assemble_support(out, bridge, observer, tray):
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
    invoke('tar', '--exclude=.git', '-czf', out / 'arlinux-support-source.tar.gz',
           'arlinux/components/steamworks', 'arlinux/components/windows-integration/accessibility',
           'arlinux/components/windows-integration/tray', 'arlinux/components/steamworks/build.sh',
           'arlinux/components/windows-integration/build-accessibility.sh',
           'arlinux/components/windows-integration/build-tray.sh', '-C', support, 'steamworks-source.tar.gz')
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
