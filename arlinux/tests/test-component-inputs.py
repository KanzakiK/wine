"""Prevent unrelated commits from invalidating compilation or hosted requests."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'arlinux/build'))
from component_inputs import source_inputs, request_identity, requirements


class InputTests(unittest.TestCase):
    def test_content_identity_tracks_core_and_recipes_but_not_other_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args]).decode().strip()
            git('init', '-q')
            def commit(path, text):
                file = root/path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text)
                git('add', '.')
                git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
                return git('rev-parse', 'HEAD')
            commit('arlinux/build/github-inputs.json', json.dumps({'mingw': {'sha256': 'compiler'}}))
            first = commit('dlls/core.c', 'code')
            plan = {'stages': {'wine-pe-aarch64': {'runner': 'ubuntu-24.04'}}}
            identity = lambda revision: source_inputs(root, revision, 'wine-pe-aarch64', plan)
            baseline = identity(first)
            docs = commit('arlinux/BUILD.md', 'new documentation')
            self.assertEqual(baseline, identity(docs))
            fex = commit('arlinux/build/fex-windows.sh', 'different unrelated recipe')
            self.assertEqual(baseline, identity(fex))
            recipe = commit('arlinux/build/wine-pe.sh', 'changed compiler flags')
            self.assertNotEqual(baseline, identity(recipe))
            core = commit('dlls/core.c', 'fixed code')
            self.assertNotEqual(identity(recipe), identity(core))

    def test_request_preserves_provenance_without_using_commit_as_a_cache_key(self):
        original = dict(format=2, stage='test', framework='a'*40, sourceInputs={'sha256': 'content'}, dependencies=[])
        self.assertEqual(request_identity(original), request_identity(dict(original, framework='b'*40)))
        self.assertNotEqual(request_identity(original), request_identity(dict(original, dependencies=[{'identity': 'new'}])))
        self.assertNotEqual(request_identity(original), request_identity(dict(original, sourceInputs={'sha256': 'modified'})))

    def test_bootstrap_only_fetches_required_sources_and_tools(self):
        plan = json.loads((Path(__file__).resolve().parents[2]/'arlinux/build/github-components.json').read_text())
        modules, resources = requirements('wine-pe-aarch64', plan)
        self.assertEqual(modules, ['arlinux/components/windows-integration'])
        self.assertEqual(resources, {'mingw'})
        modules, resources = requirements('wine-pulse', plan)
        self.assertEqual(modules, ['arlinux/components/pulseaudio-android'])
        self.assertEqual(resources, {'ndk'})


if __name__ == '__main__':
    unittest.main()
