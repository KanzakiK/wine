"""Content-addressed Bionic runtime components, produced only by the final graph stage."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

COMPONENT_TAG = 'arlinux-wine-components'
COMPONENT_BASE = 'https://github.com/taowen/wine/releases/download/'+COMPONENT_TAG+'/'
INDEX = 'arlinux-wine-runtime.json'


def finish(final, output, records):
    output.mkdir(parents=True, exist_ok=True)
    for source in final.iterdir():
        if source.is_file():
            shutil.copyfile(source, output/source.name)
    target = output/INDEX
    pending = output/'runtime.json.part'
    pending.write_text(json.dumps(dict(format=1, wineManifestSha256=sha(target), stages=records), indent=2)+'\n')
    pending.replace(output/'runtime.json')
    print('Independent Wine runtime ready: '+str(target), flush=True)


def publish_distribution(data, record, final):
    """The completion marker follows every immutable object upload."""
    index = read_index(final/INDEX)
    repository = os.environ['GITHUB_REPOSITORY']
    tag = 'arlinux-wine-product-'+data['identity'][:24]
    def run(*args):
        subprocess.run(list(map(str, args)), check=True)
    def release_assets(name):
        result = subprocess.run(['gh', 'api', f'repos/{repository}/releases/tags/{name}'],
                                capture_output=True, text=True)
        if result.returncode:
            run('gh', 'release', 'create', name, '--repo', repository, '--prerelease',
                '--title', name, '--notes', 'Immutable ARLinux build inputs; not a latest runtime promotion.')
            return {}
        return {asset['name']: asset for asset in json.loads(result.stdout)['assets']}
    objects, assets = release_assets(COMPONENT_TAG), release_assets(tag)
    def upload(path, name, release, existing):
        checksum, size = sha(path), path.stat().st_size
        if name in existing:
            prior = existing[name]
            if prior.get('digest') != 'sha256:'+checksum or prior['size'] != size:
                raise ValueError('Immutable product asset conflicts: '+name)
        else:
            with tempfile.TemporaryDirectory(prefix='product-asset-') as directory:
                staged = Path(directory)/name
                shutil.copyfile(path, staged)
                run('gh', 'release', 'upload', release, '--repo', repository, staged)
            existing[name] = dict(digest='sha256:'+checksum, size=size)
        return checksum, size
    component_files = {item['file'] for item in index['components']}
    record['artifacts'], record['parts'] = [], []
    for path in sorted(final.iterdir()):
        if not path.is_file():
            continue
        role = 'runtime' if path.name in component_files else 'manifest' if path.name == INDEX else 'source'
        if role == 'source':
            name, release, existing = 'source-'+sha(path)+'.tar.gz', COMPONENT_TAG, objects
        elif role == 'runtime':
            name, release, existing = path.name, COMPONENT_TAG, objects
        else:
            name, release, existing = path.name, tag, assets
        checksum, size = upload(path, name, release, existing)
        record['artifacts'].append(dict(name=path.name, sha256=checksum, bytes=size, role=role,
            url=f'https://github.com/{repository}/releases/download/{release}/{name}'))
    manifest = final.parent/'wine-component.json'
    manifest.write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
    upload(manifest, 'component.json', tag, assets)


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def component_name(name):
    """Partition actual output paths, not a list of required DLLs/features."""
    path = Path(name)
    if 'fex' in path.name.lower():
        return 'fex'
    for prefix, group in (
        ('files/etc/', 'configuration'),
        ('files/share/fex-emu/', 'configuration'),
        ('files/lib/arlinux/', 'integration'),
        ('files/share/arlinux/fonts/', 'fonts'),
        ('files/share/wine/fonts/', 'fonts'),
        ('files/lib/wine/dxvk/', 'dxvk'),
        ('files/lib/wine/aarch64-windows/', 'wine-pe-arm64'),
        ('files/lib/wine/x86_64-windows/', 'wine-pe-x64'),
        ('files/lib/wine/i386-windows/', 'wine-pe-x86'),
        ('files/lib/wine/aarch64-unix/', 'wine-native'),
    ):
        if name.startswith(prefix):
            return group
    return 'wine-data'


def assemble(root, output):
    metadata = json.loads((root/'bionic-runtime.json').read_text())
    groups = {}
    for path in sorted(root.rglob('*')):
        if path.is_dir() and not path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        if name == 'bionic-runtime.json':
            continue
        groups.setdefault(component_name(name), []).append(path)
    def archive_group(item):
        group, paths = item
        pending = output/(group+'.tar.gz.part')
        with pending.open('wb') as target, gzip.GzipFile(filename='', mode='wb', fileobj=target,
                                                        compresslevel=1, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as archive:
                for path in paths:
                    entry = archive.gettarinfo(str(path), path.relative_to(root).as_posix())
                    entry.uid = entry.gid = entry.mtime = 0
                    entry.uname = entry.gname = ''
                    if entry.isfile():
                        with path.open('rb') as source:
                            archive.addfile(entry, source)
                    else:
                        archive.addfile(entry)
        checksum = sha(pending)
        name = group+'-'+checksum+'.tar.gz'
        archive = output/name
        pending.rename(archive)
        return dict(name=group, file=name, sha256=checksum,
                    bytes=archive.stat().st_size, url=COMPONENT_BASE+name)
    # gzip releases the GIL. Independent archives can use the runner's cores
    # without changing group ordering, tar metadata or compressed output bytes.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        components = list(pool.map(archive_group, sorted(groups.items())))
    sources = []
    for path in sorted(output.glob('*.tar.gz')):
        if path.name in {item['file'] for item in components}:
            continue
        checksum = sha(path)
        sources.append(dict(file=path.name, sha256=checksum, bytes=path.stat().st_size,
                            url=COMPONENT_BASE+'source-'+checksum+'.tar.gz'))
    index = dict(format=1, kind='arlinux-bionic-components', runtime=metadata,
                 components=components, sources=sources)
    (output/INDEX).write_text(json.dumps(index, sort_keys=True, indent=2)+'\n')


def read_index(path):
    path = Path(path)
    index = json.loads(path.read_text())
    if (index.get('format') != 1 or index.get('kind') != 'arlinux-bionic-components'
            or index['runtime'].get('libc') != 'bionic' or not index.get('components')):
        raise ValueError('Expected a Bionic runtime component manifest')
    seen = set()
    for item in index['components']:
        if (not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or not re.fullmatch(r'[a-z0-9-]+-'+item['sha256']+r'\.tar\.gz', item['file'])
                or item['url'] != COMPONENT_BASE+item['file'] or item['name'] in seen):
            raise ValueError('Invalid runtime component')
        seen.add(item['name'])
        component = path.parent/item['file']
        if component.stat().st_size != item['bytes'] or sha(component) != item['sha256']:
            raise ValueError('Runtime component differs from its build manifest: '+item['name'])
    return index
