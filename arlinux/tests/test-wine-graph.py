import importlib.util
from pathlib import Path
import tempfile
import unittest

spec_wine = importlib.util.spec_from_file_location('wine_pipeline',
    Path(__file__).resolve().parents[2] / 'arlinux/build/wine-pipeline.py')
wine_pipeline = importlib.util.module_from_spec(spec_wine)
spec_wine.loader.exec_module(wine_pipeline)


class WineGraphTest(unittest.TestCase):
    def test_source_chain_passes_matching_native_and_pe_inputs_and_reuses_stages(self):
        import json
        import tarfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = wine_pipeline.ComponentCache(root / 'cache')
            (root / 'arlinux').mkdir()
            (root / 'arial.ttf').write_text('fixture font')
            (root / 'arlinux/wine_fonts.py').write_text(
                "from pathlib import Path\nFILES = ('arial.ttf',)\n"
                "def source_directory(): return Path(__file__).resolve().parents[1]\n")
            env, calls = {}, []
            paths = {name: root / name for name in ('wineSource', 'mingw', 'ndk', 'bionicPrefix', 'addons')}
            paths['bionicPrefix'] = cache.stage('bionic-deps', {'fixture':'matching headers'}, lambda output: output.mkdir(parents=True))
            common = dict(sources={}, wineSources={'commit': 'pinned'}, pulseRecipe={})
            def invoke(*command):
                calls.append(command)
                recipe = Path(command[1]).name
                out = Path(command[-1])
                if 'pulseaudio-android' in str(command[1]):
                    out = Path(env['ARLINUX_PULSE_WORK']) / 'prefix'
                    out.mkdir(parents=True)
                elif recipe == 'package-wine-pe.py':
                    merged = Path(command[command.index('--wine') + 1])
                    self.assertEqual((merged/'files/include/wine/iaccessible2.h').read_text(), 'generated aarch64 header')
                    for arch in ('aarch64', 'x86_64', 'i386'):
                        self.assertEqual((merged/f'files/lib/wine/{arch}-windows/test.dll').read_text(), arch)
                    source = out.parent / 'dummy'
                    source.write_text('PE modules')
                    with tarfile.open(out, 'w:gz') as archive:
                        archive.add(source, arcname='pe-module')
                    for name in ('wine', 'fex', 'dxvk'):
                        (out.parent / f'pe-{name}-source.tar.gz').write_text(name)
                elif recipe == 'wine-pe.sh':
                    tools = out / 'tools'
                    tools.mkdir(parents=True)
                    (tools / 'winegcc').write_text('matching compiler')
                    arch = env['ARLINUX_WINE_PE_ARCH']
                    modules = out / f'files/lib/wine/{arch}-windows'
                    modules.mkdir(parents=True)
                    (modules/'test.dll').write_text(arch)
                    header = out/'files/include/wine/iaccessible2.h'
                    header.parent.mkdir(parents=True)
                    header.write_text('generated '+arch+' header')
                    (out / 'build-state.json').write_text(json.dumps({'tools': str(tools)}))
                elif recipe == 'wine-bionic.sh':
                    out.mkdir()
                    for name in ('source', 'core'):
                        (out / name).mkdir()
                        (out / name / 'abi').write_text('native ABI')
                    (out / 'build-state.json').write_text(json.dumps({n: str(out/n) for n in ('source', 'core')}))
                    Path(env['BIONIC_ARCHIVE']).write_text('Bionic Wine archive')
                    self.assertEqual(env['BIONIC_VULKAN_DRIVER'], 'system')
                    self.assertEqual(env['BIONIC_OPENGL'], 'zink')
                    self.assertTrue(Path(env['BIONIC_PULSE_PREFIX']).is_dir())
                    self.assertTrue(Path(env['BIONIC_SYSTEM_VULKAN_ADAPTER']).is_file())
                    self.assertTrue((Path(command[-2]) / 'pe-module').is_file())
                else:
                    out.mkdir()
                    (out / 'prefix').mkdir()
                    if recipe == 'build-bionic-vulkan.py':
                        (out / 'libvulkan_android_desktop.so').touch()
            archive = wine_pipeline.build_wine(cache, root, root, paths.copy(), common, invoke, env)
            self.assertEqual(archive.read_text(), 'Bionic Wine archive')
            self.assertTrue((archive.parent / 'pe-fex-source.tar.gz').is_file())
            self.assertEqual(len(calls), 11)
            self.assertNotIn('BIONIC_ARCHIVE', env)
            again = wine_pipeline.build_wine(cache, root, root, paths.copy(), common, invoke, env)
            self.assertEqual(archive, again)
            self.assertEqual(len(calls), 11)


if __name__ == '__main__': unittest.main()
