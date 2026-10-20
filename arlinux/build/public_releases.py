"""Prepare and promote fixed per-producer releases from verified build outputs."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import urlparse

from runtime_distribution import INDEX, sha


def prepare(selection):
    """Only publication packaging; no compiler, SDK capsule or old runtime input."""
    selection = Path(selection)
    catalog = json.loads(selection.read_text())
    if catalog.get('format') != 2:
        raise ValueError('Publication requires the tested independent producer product')
    directory = selection.parent/'public-release'
    directory.mkdir(exist_ok=True)
    # These modules share private Wine/FEX interfaces. Data and Vulkan clients
    # remain independently updateable; incompatible snapshots are never selected.
    paired = [m for m in catalog['manifests'] if m['name'].startswith('wine-pe-')
              or m['name'] in ('wine-bionic', 'fex', 'steamworks')]
    abi = hashlib.sha256(json.dumps([(m['name'], m['sha256']) for m in paired],
                                   separators=(',', ':')).encode()).hexdigest()

    def package(item):
        leaf = json.loads((selection.parent/item['file']).read_text())
        metadata = dict(leaf['runtime'])
        if 'wineSource' in metadata:
            source = metadata['wineSource']
            source['archiveURL'] = next(s['url'] for s in leaf['sources']
                                        if s['sha256'] == source['archiveSHA256'])
        if item in paired:
            metadata['compatibility'] = {'wine': abi}
        # Source references remain the producer's verified immutable URLs.
        metadata['sources'] = leaf['sources']
        raw_metadata = (json.dumps(metadata, sort_keys=True)+'\n').encode()
        pending = directory/(item['name']+'.tar.gz.part')
        with pending.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb',
                                                    compresslevel=1, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as output:
                entry = tarfile.TarInfo('bionic-runtime.json')
                entry.size, entry.mode = len(raw_metadata), 0o644
                output.addfile(entry, io.BytesIO(raw_metadata))
                for component in leaf['components']:
                    with tarfile.open(selection.parent/component['file']) as source:
                        for member in source:
                            output.addfile(member, source.extractfile(member) if member.isfile() else None)
        checksum = sha(pending)
        filename = item['name']+'-'+checksum+'.tar.gz'
        pending.replace(directory/filename)
        repository = '/'.join(urlparse(item['url']).path.split('/')[1:3])
        tag = 'arlinux-'+item['name']+'-latest'
        return dict(name=item['name'], file=filename, sha256=checksum,
                    bytes=(directory/filename).stat().st_size, asset='runtime.tar.gz',
                    url=f'https://github.com/{repository}/releases/download/{tag}/runtime.tar.gz',
                    repository=repository, tag=tag, metadata=metadata)

    with ThreadPoolExecutor(max_workers=4) as pool:
        packages = list(pool.map(package, catalog['manifests']))
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
    candidate = dict(format=1, kind='arlinux-bionic-components', embeddedMetadata=True,
                     runtime=runtime, components=[{k: v for k, v in p.items()
                                                  if k not in ('metadata', 'repository', 'tag')}
                                                 for p in packages])
    target = directory/INDEX
    target.write_text(json.dumps(candidate, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')
    # The ordinary Debug cache transfer verifies this publication product just
    # like its compiler product. No installed prefix or instance is transferred.
    receipt = json.loads((selection.parent/'download-receipt.json').read_text())
    record = selection.parent/'github-component.json'
    shutil.copyfile(record, directory/record.name)
    receipt['files'] = {p['file']: p['sha256'] for p in packages}
    receipt['files'][INDEX] = sha(target)
    receipt['files'][record.name] = sha(directory/record.name)
    receipt['publicationInput'] = sha(selection)
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
        if sha(directory/name) != checksum:
            raise ValueError('Prepared publication changed: '+name)
    product = json.loads((directory/INDEX).read_text())
    for item in product['components']:
        parts = urlparse(item['url']).path.split('/')
        repository, tag = '/'.join(parts[1:3]), parts[5]
        endpoint = f'repos/{repository}/releases/tags/{tag}'
        view = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
        if view.returncode:
            subprocess.run(['gh', 'release', 'create', tag, '--repo', repository,
                            '--title', 'ARLinux '+item['name'], '--notes',
                            'Current ARLinux runtime component. Updated in place; downloads verified by SHA-256.',
                            '--latest=false'], check=True)
            assets = []
        else:
            assets = json.loads(view.stdout)['assets']
        current = next((a for a in assets if a['name'] == item['asset']), None)
        if not current or current.get('digest') != 'sha256:'+item['sha256'] or current['size'] != item['bytes']:
            with tempfile.TemporaryDirectory(prefix='arlinux-publish-') as temporary:
                target = Path(temporary)/item['asset']
                shutil.copyfile(directory/item['file'], target)
                subprocess.run(['gh', 'release', 'upload', tag, '--repo', repository,
                                str(target), '--clobber'], check=True)
        published = json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))
        asset = next(a for a in published['assets'] if a['name'] == item['asset'])
        if asset.get('digest') != 'sha256:'+item['sha256'] or asset['size'] != item['bytes']:
            raise RuntimeError('Published component differs: '+item['name'])
        print('Published fixed release:', repository, tag, item['sha256'], flush=True)
