"""Assemble the final runtime on the workstation from verified runner capsules.

Linux paths, permissions and links remain tar metadata; no Linux filesystem or
compiler is needed on the coordinator host. Called only by github-products.py.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import copy
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import tarfile

from artifact_download import download, download_capsule, sha256_file
from runtime_distribution import COMPONENT_BASE, INDEX, component_name, read_index, publish_distribution


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '\\' in name or ':' in name
            or '..' in path.parts or str(path) != name.rstrip('/')):
        raise ValueError('Unsafe capsule member: '+name)
    return path.as_posix()


def unpack_capsule(reference, directory):
    manifest = download(reference['manifestUrl'], directory/'component.json', reference['manifestSha256'])
    record = json.loads(manifest.read_text())
    if record['identity'] != reference['identity']:
        raise ValueError('Assembly dependency identity mismatch')
    prefix = safe_name(record['pipelineOutput'])+'/'
    if not prefix.startswith('framework/build/pipeline/'+record['stage']+'/'):
        raise ValueError('Assembly dependency output escapes its declared stage')
    packed = download_capsule(record, directory)
    import zstandard
    decoded = directory/'capsule.tar'
    with packed.open('rb') as source, decoded.open('wb') as target:
        with zstandard.ZstdDecompressor().stream_reader(source) as stream:
            shutil.copyfileobj(stream, target)
    return record, prefix, decoded


def scan_capsule(path, prefix, runtime, groups, sources, output):
    """Select only the declared output, never a compiler tree or its references."""
    metadata = None
    names = set()
    with tarfile.open(path, 'r:') as archive:
        for entry in archive:
            name = safe_name(entry.name)
            if not name.startswith(prefix):
                continue
            relative = name[len(prefix):]
            if not relative or entry.isdir():
                continue
            if relative in names:
                raise ValueError('Duplicate assembly input: '+relative)
            names.add(relative)
            if runtime and relative == 'runtime/bionic-runtime.json':
                if not entry.isfile() or entry.size > 16*1024*1024:
                    raise ValueError('Invalid Bionic metadata')
                metadata = json.load(archive.extractfile(entry))
                continue
            if runtime and relative.startswith('runtime/'):
                name = relative[len('runtime/'):]
                if name == 'build-state.json':
                    continue
                link_prefix = prefix+'runtime/'
            elif not runtime and relative.startswith('steamworks/'):
                name = 'files/lib/arlinux/'+relative
                link_prefix = prefix
            elif not runtime and '/' not in relative and relative.endswith('.exe'):
                name = 'files/lib/arlinux/'+relative
                link_prefix = prefix
            elif (runtime and '/' not in relative and relative.endswith('.tar.gz')
                  or not runtime and relative == 'arlinux-support-source.tar.gz'):
                if not entry.isfile() or relative in sources:
                    raise ValueError('Invalid or duplicate component source: '+relative)
                with (output/relative).open('wb') as target:
                    shutil.copyfileobj(archive.extractfile(entry), target)
                sources.add(relative)
                continue
            else:
                continue
            entry = copy.copy(entry)
            entry.name = safe_name(name)
            entry.uid = entry.gid = entry.mtime = 0
            entry.uname = entry.gname = ''
            entry.pax_headers = {}
            if entry.islnk():
                target = safe_name(entry.linkname)
                if not target.startswith(link_prefix):
                    raise ValueError('Hard link escapes its component output')
                entry.linkname = target[len(link_prefix):]
                if not runtime:
                    entry.linkname = 'files/lib/arlinux/'+entry.linkname
            elif entry.issym():
                if ('\\' in entry.linkname or ':' in entry.linkname
                        or entry.linkname.startswith('/')
                        or posixpath.normpath(posixpath.join(posixpath.dirname(name), entry.linkname)).startswith('../')):
                    raise ValueError('Symbolic link escapes the runtime')
            elif not entry.isfile():
                raise ValueError('Unsupported runtime member type: '+name)
            groups.setdefault(component_name(name), []).append((path, entry))
    return metadata


def write_group(item, output):
    group, members = item
    pending = output/(group+'.tar.gz.part')
    hashes, links, seen = {}, {}, set()
    with ExitStack() as stack:
        inputs = {path: stack.enter_context(tarfile.open(path, 'r:')) for path in {path for path, _ in members}}
        raw = stack.enter_context(pending.open('wb'))
        zipped = stack.enter_context(gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1, mtime=0))
        archive = stack.enter_context(tarfile.open(fileobj=zipped, mode='w|'))
        for path, entry in sorted(members, key=lambda pair: pair[1].name):
            if entry.name in seen:
                raise ValueError('Duplicate runtime path: '+entry.name)
            seen.add(entry.name)
            if entry.isfile():
                source = inputs[path].extractfile(entry)
                hashes[entry.name] = hashlib.file_digest(source, 'sha256').hexdigest()
                source.seek(0)
                archive.addfile(entry, source)
                source.close()
            else:
                archive.addfile(entry)
                links[entry.name] = (entry.linkname if entry.islnk() else
                    posixpath.normpath(posixpath.join(posixpath.dirname(entry.name), entry.linkname)))
    checksum = sha256_file(pending)
    name = group+'-'+checksum+'.tar.gz'
    pending.replace(output/name)
    return dict(name=group, file=name, sha256=checksum,
                bytes=(output/name).stat().st_size, url=COMPONENT_BASE+name), hashes, links


def assemble(request, directory):
    output = directory/'product'
    receipt = directory/'assembly-receipt.json'
    try:
        prior = json.loads(receipt.read_text())
        if (prior['request'] == request and prior['files']
                and all(sha256_file(output/name) == checksum for name, checksum in prior['files'].items())):
            read_index(output/INDEX)
            print('OK verified local assembly '+request['identity'], flush=True)
            return output
    except (OSError, ValueError, KeyError):
        pass
    # This directory is exclusively owned by the request lock. Clear only its
    # unfinished regular output files; no input cache or other product is removed.
    output.mkdir(parents=True, exist_ok=True)
    for path in output.iterdir():
        if not path.is_file() or path.is_symlink():
            raise ValueError('Unexpected local assembly output: '+str(path))
        path.unlink()
    decoded, groups, sources, metadata = [], {}, set(), None
    try:
        for reference in request['dependencies']:
            record, prefix, path = unpack_capsule(reference, directory/'inputs'/reference['identity'])
            decoded.append(path)
            if record['stage'] not in ('wine-bionic', 'runtime-support'):
                raise ValueError('Unexpected final assembly dependency')
            current = scan_capsule(path, prefix, record['stage'] == 'wine-bionic', groups, sources, output)
            if current is not None:
                metadata = current
        if metadata is None:
            raise ValueError('Missing Bionic runtime metadata')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda item: write_group(item, output), sorted(groups.items())))
        hashes, links = {}, {}
        for _, files, aliases in results:
            if set(hashes).intersection(files) or set(links).intersection(aliases):
                raise ValueError('Duplicate paths across runtime components')
            hashes.update(files)
            links.update(aliases)
        # Match the filesystem packager's file-symlink hashes without creating
        # symlinks on Windows. Directory/dangling links have no file digest.
        for name in links:
            target, visited = name, set()
            while target in links:
                if target in visited:
                    raise ValueError('Cyclic runtime link: '+name)
                visited.add(target)
                target = links[target]
            if target in hashes:
                hashes[name] = hashes[target]
        metadata['files'] = dict(sorted(hashes.items()))
        metadata['support'] = dict(protocol=1, directory='files/lib/arlinux')
        support = output/'arlinux-support-source.tar.gz'
        metadata['originalSources']['support'] = dict(asset=support.name, sha256=sha256_file(support))
        index = dict(format=1, kind='arlinux-bionic-components', runtime=metadata,
            components=[record for record, _, _ in results],
            sources=[dict(file=name, sha256=sha256_file(output/name), bytes=(output/name).stat().st_size,
                          url=COMPONENT_BASE+'source-'+sha256_file(output/name)+'.tar.gz') for name in sorted(sources)])
        (output/INDEX).write_text(json.dumps(index, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')
        read_index(output/INDEX)
        state = dict(request=request, files={path.name: sha256_file(path) for path in output.iterdir()})
        pending = receipt.with_suffix('.tmp')
        pending.write_text(json.dumps(state, sort_keys=True)+'\n', encoding='utf-8', newline='\n')
        pending.replace(receipt)
        return output
    finally:
        for path in decoded:
            path.unlink(missing_ok=True)


def build(request, directory, repository, object_cache):
    final = assemble(request, directory)
    record = dict(request)
    record['outputIdentity'] = hashlib.sha256(json.dumps(
        {path.name: sha256_file(path) for path in sorted(final.iterdir())}, sort_keys=True).encode()).hexdigest()
    publish_distribution(request, record, final, repository=repository)
    # fetch_product uses this same content-addressed cache. Never upload a
    # locally assembled product only to download its identical bytes again.
    object_cache.mkdir(parents=True, exist_ok=True)
    for path in final.iterdir():
        checksum = sha256_file(path)
        pending = object_cache/(checksum+'.local-part')
        shutil.copyfile(path, pending)
        if sha256_file(pending) != checksum:
            raise ValueError('Local product changed while caching')
        pending.replace(object_cache/checksum)
