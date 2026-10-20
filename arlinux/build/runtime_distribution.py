"""Independent Bionic runtime manifests and immutable component publication."""
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
INDEX = 'arlinux-wine-manifests.json'
LEAF_INDEX = 'arlinux-wine-runtime.json'
RUNTIME_STAGES = ('wine-bionic', 'steamworks', 'windows-accessibility', 'windows-tray')


def publish_runtime_component(data, framework):
    """Publish a producer's own installable files and source manifest."""
    from pipeline_cache import inventory, build_references
    descriptor = json.loads((framework/'build/artifacts/components'/f'{data["stage"]}.json').read_text())
    state = descriptor['records'][data['stage']]
    built = Path(descriptor['output'])
    if inventory(built) != state['outputs'] or build_references(built) != state['references']:
        raise ValueError('Runtime producer differs from its verified build receipt')
    record = dict(data, outputIdentity=hashlib.sha256(json.dumps(dict(
        outputs=state['outputs'], references=state['references']), sort_keys=True).encode()).hexdigest())
    repository = os.environ['GITHUB_REPOSITORY']
    base = f'https://github.com/{repository}/releases/download/{COMPONENT_TAG}/'
    with tempfile.TemporaryDirectory(prefix='runtime-publication-', dir=framework/'build/artifacts') as temporary:
        work = Path(temporary)
        output = work/'publication'
        output.mkdir()
        stage = data['stage']
        if stage == 'wine-bionic':
            runtime = built/'runtime'
            for source in built.glob('*.tar.gz'):
                shutil.copyfile(source, output/source.name)
        else:
            runtime = work/'runtime'
            target = runtime/'files/lib/arlinux'
            target.mkdir(parents=True)
            if stage == 'steamworks':
                target = target/'steamworks'
                shutil.copytree(built, target, ignore=shutil.ignore_patterns('*-source.tar.gz'))
                source = output/'steamworks-source.tar.gz'
                shutil.copyfile(built/source.name, source)
            else:
                for binary in built.iterdir():
                    if binary.is_file():
                        shutil.copyfile(binary, target/binary.name)
                source = output/(stage+'-source.tar.gz')
                module = framework/'arlinux/components/windows-integration'
                with source.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
                    process = subprocess.Popen(['git', '-C', str(module), 'archive', '--format=tar', 'HEAD'], stdout=subprocess.PIPE)
                    try:
                        shutil.copyfileobj(process.stdout, compressed)
                    finally:
                        process.stdout.close()
                    if process.wait():
                        raise RuntimeError('Cannot archive the pinned Windows integration sources')
            metadata = dict(protocol=1, libc='bionic', support=dict(protocol=1, directory='files/lib/arlinux'),
                originalSources={stage: dict(asset=source.name, sha256=sha(source))},
                files={path.relative_to(runtime).as_posix(): sha(path)
                       for path in sorted(runtime.rglob('*')) if path.is_file()})
            (runtime/'bionic-runtime.json').write_text(json.dumps(metadata, sort_keys=True)+'\n')
        name = 'arlinux-'+stage+'.json'
        assemble(runtime, output, component_base=base,
                 group_prefix='' if stage == 'wine-bionic' else stage+'-', index_name=name)
        publish_distribution(data, record, output, repository=repository, index_name=name)


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


def publish_distribution(data, record, final, repository=None, index_name=INDEX):
    """The completion marker follows every immutable object upload."""
    index = json.loads((final/index_name).read_text())
    repository = repository or os.environ['GITHUB_REPOSITORY']
    tag = 'arlinux-'+data['stage']+'-'+data['identity'][:24]
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
                try:
                    run('gh', 'release', 'upload', release, '--repo', repository, staged)
                except subprocess.CalledProcessError:
                    # Another product may publish the same content-addressed
                    # object after our release inventory was fetched. Never
                    # clobber it; accept only its exact verified bytes.
                    concurrent = release_assets(release).get(name)
                    if (not concurrent or concurrent.get('digest') != 'sha256:'+checksum
                            or concurrent['size'] != size):
                        raise
                    print('Verified concurrent immutable upload: '+name, flush=True)
            existing[name] = dict(digest='sha256:'+checksum, size=size)
        return checksum, size
    component_files = {item['file'] for item in index.get('components', [])}
    record['artifacts'], record['parts'] = [], []
    for path in sorted(final.iterdir()):
        if not path.is_file():
            continue
        role = 'runtime' if path.name in component_files else 'manifest' if path.name == index_name else 'source'
        if role == 'source':
            name, release, existing = 'source-'+sha(path)+'.tar.gz', COMPONENT_TAG, objects
        elif role == 'runtime':
            name, release, existing = path.name, COMPONENT_TAG, objects
        else:
            name, release, existing = path.name, tag, assets
        checksum, size = upload(path, name, release, existing)
        record['artifacts'].append(dict(name=path.name, sha256=checksum, bytes=size, role=role,
            url=f'https://github.com/{repository}/releases/download/{release}/{name}'))
    if data['stage'] in RUNTIME_STAGES:
        item = next(item for item in record['artifacts'] if item['role'] == 'manifest')
        record['runtimeManifest'] = dict(name=data['stage'], file=item['name'],
            sha256=item['sha256'], bytes=item['bytes'], url=item['url'])
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


def assemble(root, output, component_base=COMPONENT_BASE, group_prefix='', index_name=LEAF_INDEX):
    metadata = json.loads((root/'bionic-runtime.json').read_text())
    groups = {}
    for path in sorted(root.rglob('*')):
        if path.is_dir() and not path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        if name == 'bionic-runtime.json':
            continue
        groups.setdefault(group_prefix+component_name(name), []).append(path)
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
                    bytes=archive.stat().st_size, url=component_base+name)
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
                            url=component_base+'source-'+checksum+'.tar.gz'))
    index = dict(format=1, kind='arlinux-bionic-components', runtime=metadata,
                 componentBase=component_base, components=components, sources=sources)
    (output/index_name).write_text(json.dumps(index, sort_keys=True, indent=2)+'\n')


def runtime_url(url, filename):
    return bool(re.fullmatch(r'https://github\.com/taowen/(?:wine|arlinux-steamworks|arlinux-windows-integration)'
                            r'/releases/download/[^/]+/'+re.escape(filename), url))


def resolve_index(path, fetch=None):
    """Resolve checksum-bound producer manifests; never fetch runtime archives."""
    path = Path(path)
    index = json.loads(path.read_text())
    if index.get('format') == 1 and index.get('kind') == 'arlinux-bionic-components':
        return index
    if (index.get('format') != 2 or index.get('kind') != 'arlinux-bionic-manifests'
            or not isinstance(index.get('manifests'), list) or not index['manifests']):
        raise ValueError('Expected independently pinned Bionic runtime manifests')
    merged = dict(format=1, kind='arlinux-bionic-components', runtime={}, components=[], sources=[])
    names, paths, sources = set(), set(), {}
    for item in index['manifests']:
        name, filename, checksum = item['name'], item['file'], item['sha256']
        if (not re.fullmatch('[a-z0-9-]+', name) or filename != 'arlinux-'+name+'.json'
                or name in names or not re.fullmatch('[0-9a-f]{64}', checksum)
                or not runtime_url(item['url'], filename)
                or type(item['bytes']) is not int or item['bytes'] <= 0):
            raise ValueError('Invalid independent runtime manifest')
        names.add(name)
        leaf = Path(fetch(item)) if fetch else path.parent/filename
        if sha(leaf) != checksum or leaf.stat().st_size != item['bytes']:
            raise ValueError('Runtime manifest checksum/size mismatch: '+name)
        child = json.loads(leaf.read_text())
        if child.get('format') != 1 or child.get('kind') != 'arlinux-bionic-components':
            raise ValueError('Expected a leaf runtime component manifest')
        for key, value in child['runtime'].items():
            if key in ('files', 'originalSources'):
                previous = merged['runtime'].setdefault(key, {})
                for field, content in value.items():
                    if field in previous and previous[field] != content:
                        raise ValueError('Conflicting runtime metadata: '+field)
                    if key == 'files' and field in previous:
                        raise ValueError('Runtime file owned by multiple producers: '+field)
                    previous[field] = content
            elif key in merged['runtime'] and merged['runtime'][key] != value:
                raise ValueError('Conflicting runtime metadata: '+key)
            else:
                merged['runtime'][key] = value
        for component in child['components']:
            if component['file'] in paths:
                raise ValueError('Duplicate independently published component')
            paths.add(component['file'])
            merged['components'].append(component)
        for source in child['sources']:
            if source['file'] in sources and sources[source['file']] != source:
                raise ValueError('Conflicting component source archive')
            sources[source['file']] = source
    merged['sources'] = list(sources.values())
    return merged


def read_index(path):
    path = Path(path)
    index = resolve_index(path)
    if (index.get('format') != 1 or index.get('kind') != 'arlinux-bionic-components'
            or index['runtime'].get('libc') != 'bionic' or not index.get('components')):
        raise ValueError('Expected a Bionic runtime component manifest')
    seen = set()
    for item in index['components']:
        if (not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or not re.fullmatch(r'[a-z0-9-]+-'+item['sha256']+r'\.tar\.gz', item['file'])
                or not runtime_url(item['url'], item['file']) or item['name'] in seen):
            raise ValueError('Invalid runtime component')
        seen.add(item['name'])
        component = path.parent/item['file']
        if component.stat().st_size != item['bytes'] or sha(component) != item['sha256']:
            raise ValueError('Runtime component differs from its build manifest: '+item['name'])
    return index
