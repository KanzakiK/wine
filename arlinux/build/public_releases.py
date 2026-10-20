"""Runner-owned candidate packaging and promotion of exact tested runtime bytes."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from artifact_download import download
from runtime_distribution import INDEX, RUNTIME_STAGES, resolve_index, runtime_url, sha

DIRECTORY = Path(__file__).resolve().parent
PLAN = json.loads((DIRECTORY/'github-components.json').read_text())


def coordinator():
    return importlib.import_module('github-products')


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def owner(stage):
    if stage not in RUNTIME_STAGES:
        raise ValueError('Not a runtime producer: '+stage)
    return PLAN['stages'][stage]['repository']


def verify_file(path, checksum, size=None):
    if (not re.fullmatch('[0-9a-f]{64}', checksum) or sha(path) != checksum
            or size is not None and path.stat().st_size != size):
        raise ValueError('Publication input hash/size mismatch: '+str(path))


def asset(repository, tag, name):
    release = coordinator().api(f'repos/{repository}/releases/tags/{tag}', optional=True)
    return next((a for a in release['assets'] if a['name'] == name), None) if release else None


def descriptor(value):
    checksum = value.get('digest', '')
    if (not re.fullmatch('sha256:[0-9a-f]{64}', checksum) or value.get('state') != 'uploaded'
            or type(value.get('size')) is not int or value['size'] <= 0):
        raise ValueError('GitHub asset has no complete SHA-256/size')
    return dict(url=value['browser_download_url'], sha256=checksum[7:], bytes=value['size'])


def metadata(leaf, abi):
    result = json.loads(json.dumps(leaf['runtime']))
    if 'wineSource' in result:
        source = result['wineSource']
        source['archiveURL'] = next(s['url'] for s in leaf['sources']
                                   if s['sha256'] == source['archiveSHA256'])
    if abi:
        result['compatibility'] = {'wine': abi}
    result['sources'] = leaf['sources']
    return result


def dispatch(stage, action, **fields):
    framework = subprocess.check_output(['git', '-C', str(DIRECTORY), 'rev-parse', 'HEAD'], text=True).strip()
    request = dict(operation='release', action=action, stage=stage,
                   recipeSHA256=sha(Path(__file__)), **fields)
    request['identity'] = identity(request)
    request['framework'] = framework
    repository = owner(stage)
    coordinator().dispatch_release(repository, request, PLAN['workflow'])
    return repository, request


def prepare(selection):
    """Dispatch delivery packaging; retain only small verified metadata locally."""
    selection = Path(selection)
    catalog = json.loads(selection.read_text())
    resolve_index(selection)
    if catalog.get('format') != 2:
        raise ValueError('Publication requires the independent producer product')
    importlib.import_module('install-github-workflows').ensure_workflows(
        {owner(item['name']) for item in catalog['manifests']})
    receipt = json.loads((selection.parent/'download-receipt.json').read_text())
    verify_file(selection, receipt['files'][selection.name])
    paired = [m for m in catalog['manifests'] if m['name'].startswith('wine-pe-')
              or m['name'] in ('wine-bionic', 'fex', 'steamworks')]
    abi = hashlib.sha256(json.dumps([(m['name'], m['sha256']) for m in paired],
                                   separators=(',', ':')).encode()).hexdigest()
    directory = selection.parent/'public-release'
    directory.mkdir(exist_ok=True)

    def candidate(item):
        leaf_path = selection.parent/item['file']
        verify_file(leaf_path, item['sha256'], item['bytes'])
        leaf = json.loads(leaf_path.read_text())
        repository, request = dispatch(item['name'], 'candidate', manifest=item,
                                        compatibility=abi if item in paired else None)
        published = asset(repository, 'arlinux-'+item['name']+'-candidates', request['identity']+'.tar.gz')
        if not published:
            raise ValueError('Runner did not retain the candidate archive')
        data = descriptor(published)
        return dict(name=item['name'], file=item['name']+'-'+data['sha256']+'.tar.gz',
                    asset=published['name'], **data, metadata=metadata(leaf, request['compatibility']))

    with ThreadPoolExecutor(max_workers=4) as pool:
        packages = list(pool.map(candidate, catalog['manifests']))
    runtime = {}
    for item in packages:
        for key, value in item['metadata'].items():
            if key in ('files', 'originalSources', 'compatibility'):
                target = runtime.setdefault(key, {})
                for name, content in value.items():
                    if name in target and (key == 'files' or target[name] != content):
                        raise ValueError('Conflicting producer metadata: '+name)
                    target[name] = content
            elif key == 'sources':
                continue
            elif key in runtime and runtime[key] != value:
                raise ValueError('Conflicting runtime metadata: '+key)
            else:
                runtime[key] = value
    target = directory/INDEX
    target.write_text(json.dumps(dict(format=1, kind='arlinux-bionic-components', embeddedMetadata=True,
        runtime=runtime, components=[{k: v for k, v in p.items() if k != 'metadata'} for p in packages]),
        sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')
    record = selection.parent/'github-component.json'
    shutil.copyfile(record, directory/record.name)
    receipt['files'] = {INDEX: sha(target), record.name: sha(directory/record.name)}
    receipt['publicationInput'] = sha(selection)
    receipt['remoteFiles'] = [{k: p[k] for k in ('file', 'sha256', 'bytes', 'url', 'asset')} for p in packages]
    (directory/'download-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('Prepared publication candidate:', target, flush=True)
    print('Publication candidate SHA-256:', sha(target), flush=True)
    return target


def promote(selection):
    directory = Path(selection).parent/'public-release'
    receipt = json.loads((directory/'download-receipt.json').read_text())
    if receipt['publicationInput'] != sha(selection):
        raise ValueError('Publication input changed; prepare and test again')
    for name, checksum in receipt['files'].items():
        verify_file(directory/name, checksum)
    product = json.loads((directory/INDEX).read_text())
    remote = {p['file']: p for p in receipt['remoteFiles']}

    def publish(item):
        if remote.get(item['file']) != {k: item[k] for k in ('file', 'sha256', 'bytes', 'url', 'asset')}:
            raise ValueError('Candidate differs from its prepared receipt')
        dispatch(item['name'], 'promote', candidate=item)
        published = asset(owner(item['name']), 'arlinux-'+item['name']+'-latest', 'runtime.tar.gz')
        data = descriptor(published or {})
        if data['sha256'] != item['sha256'] or data['bytes'] != item['bytes']:
            raise RuntimeError('Published component differs: '+item['name'])
        print('Published fixed release:', item['name'], item['sha256'], flush=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(publish, product['components']))


def upload(path, repository, tag, name, immutable=False):
    """Runner-local upload with GitHub digest verification; no workstation relay."""
    endpoint = f'repos/{repository}/releases/tags/{tag}'
    release = coordinator().api(endpoint, optional=True)
    if not release:
        coordinator().gh('release', 'create', tag, '--repo', repository,
                         '--title', tag, '--notes', 'ARLinux runtime component; downloads verified by SHA-256.',
                         '--latest=false')
    current = asset(repository, tag, name)
    checksum, size = sha(path), path.stat().st_size
    if current and (current.get('digest'), current['size']) == ('sha256:'+checksum, size):
        print('Verified existing asset:', tag, name, flush=True)
        return
    if current and immutable:
        raise ValueError('Immutable candidate asset changed')
    target = path.parent/name
    if target != path:
        shutil.copyfile(path, target)
    coordinator().gh('release', 'upload', tag, '--repo', repository, str(target), '--clobber')
    result = descriptor(asset(repository, tag, name) or {})
    if (result['sha256'], result['bytes']) != (checksum, size):
        raise RuntimeError('GitHub uploaded bytes differ from the verified output')


def runner():
    request = json.loads(os.environ['ARLINUX_COMPONENT_REQUEST'])
    checked = {k: v for k, v in request.items() if k not in ('identity', 'framework')}
    stage = request['stage']
    repository = owner(stage)
    if (request.get('operation') != 'release' or request['identity'] != identity(checked)
            or request['recipeSHA256'] != sha(Path(__file__))
            or repository != os.environ['GITHUB_REPOSITORY']):
        raise ValueError('Publication request/recipe/owner mismatch')
    with tempfile.TemporaryDirectory(prefix='arlinux-release-') as temporary:
        work = Path(temporary)
        if request['action'] == 'promote':
            item = request['candidate']
            expected_prefix = f'https://github.com/{repository}/releases/download/arlinux-{stage}-candidates/'
            if (not item['url'].startswith(expected_prefix)
                    or not re.fullmatch(r'[0-9a-f]{64}\.tar\.gz', item['asset'])
                    or item['url'] != expected_prefix+item['asset']):
                raise ValueError('Promotion must consume an immutable candidate from its owner')
            archive = download(item['url'], work/'runtime.tar.gz', item['sha256'])
            verify_file(archive, item['sha256'], item['bytes'])
            upload(archive, repository, 'arlinux-'+stage+'-latest', 'runtime.tar.gz')
            return
        if request['action'] != 'candidate':
            raise ValueError('Unknown release operation')
        existing = asset(repository, 'arlinux-'+stage+'-candidates', request['identity']+'.tar.gz')
        if existing:
            descriptor(existing)
            print('Reusing verified immutable candidate:', existing['name'], flush=True)
            return
        item = request['manifest']
        if (item['name'] != stage or not runtime_url(item['url'], item['file'])
                or not item['url'].startswith(f'https://github.com/{repository}/')):
            raise ValueError('Producer manifest belongs to another owner')
        leaf_path = download(item['url'], work/'manifest.json', item['sha256'])
        verify_file(leaf_path, item['sha256'], item['bytes'])
        leaf = json.loads(leaf_path.read_text())
        meta = metadata(leaf, request['compatibility'])
        if meta.get('protocol') != 1 or meta.get('libc') != 'bionic':
            raise ValueError('Expected a Bionic runtime producer')
        # Source provenance is checked here, never transported via Windows.
        for item in leaf['sources']:
            if not runtime_url(item['url'], 'source-'+item['sha256']+'.tar.gz'):
                raise ValueError('Invalid source archive URL')
            source = download(item['url'], work/('source-'+item['sha256']), item['sha256'])
            verify_file(source, item['sha256'], item['bytes'])
        raw_metadata = (json.dumps(meta, sort_keys=True)+'\n').encode()
        archive = work/'runtime.tar.gz'
        expected, seen = dict(meta['files']), set()
        with archive.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb',
                                                    compresslevel=1, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as output:
                entry = tarfile.TarInfo('bionic-runtime.json')
                entry.size, entry.mode = len(raw_metadata), 0o644
                output.addfile(entry, io.BytesIO(raw_metadata))
                for item in leaf['components']:
                    if not runtime_url(item['url'], item['file']) or Path(item['file']).name != item['file']:
                        raise ValueError('Invalid runtime archive URL/path')
                    source = download(item['url'], work/item['file'], item['sha256'])
                    verify_file(source, item['sha256'], item['bytes'])
                    with tarfile.open(source) as bundle:
                        for member in bundle:
                            tarfile.data_filter(member, str(work/'validation'))
                            name = member.name
                            if (name in seen or name == 'bionic-runtime.json' or member.isdir()
                                    or '\\' in name or ':' in name or any(p in ('', '.', '..') for p in name.split('/'))):
                                raise ValueError('Unsafe or duplicate runtime path: '+name)
                            seen.add(name)
                            if name in expected:
                                if not (member.isfile() or member.islnk()):
                                    raise ValueError('Expected runtime file: '+name)
                                if hashlib.file_digest(bundle.extractfile(member), 'sha256').hexdigest() != expected.pop(name):
                                    raise ValueError('Runtime file checksum mismatch: '+name)
                            output.addfile(member, bundle.extractfile(member) if member.isfile() else None)
        if expected:
            raise ValueError('Declared runtime files missing from producer output')
        upload(archive, repository, 'arlinux-'+stage+'-candidates', request['identity']+'.tar.gz', immutable=True)


if __name__ == '__main__':
    runner()
