"""Build independent Mono/Gecko download objects from pinned vendor archives."""
from contextlib import ExitStack
import copy
import gzip
import hashlib
import json
from pathlib import PurePosixPath
import posixpath
import sys
import tarfile
import zlib

from artifact_download import download, sha256_file
from runtime_distribution import COMPONENT_BASE, publish_distribution


def toolchain_identity():
    return dict(python=list(sys.version_info[:3]), zlib=zlib.ZLIB_RUNTIME_VERSION)


def member_name(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or '\\' in name or ':' in name or '..' in path.parts
            or not path.parts or path.as_posix() != name.rstrip('/')):
        raise ValueError('Unsafe addon archive path: '+name)
    return path.as_posix()


def build(request, directory, repository, object_cache):
    output = directory/'product'
    output.mkdir(parents=True, exist_ok=True)
    for path in output.iterdir():
        if not path.is_file() or path.is_symlink():
            raise ValueError('Unexpected addon output path')
        path.unlink()
    groups, hashes, vendors = {}, {}, []
    with ExitStack() as stack:
        for item in request['sourceInputs']['tools']['addons']:
            source = download(item['url'], object_cache/item['sha256'], item['sha256'], label=item['file'])
            vendors.append(dict(url=item['url'], sha256=item['sha256'], file=item['file']))
            archive = stack.enter_context(tarfile.open(source, 'r:*'))
            group = item['directory']
            prefix = 'files/share/wine/'+group+'/'
            members = groups.setdefault(group, {})
            for entry in archive:
                original = member_name(entry.name)
                if entry.isdir():
                    continue
                if not (entry.isfile() or entry.issym() or entry.islnk()):
                    raise ValueError('Unsupported addon archive member')
                name = prefix+original
                checksum = None
                if entry.isfile() or entry.islnk():
                    checksum = hashlib.file_digest(archive.extractfile(entry), 'sha256').hexdigest()
                # Preserve the declared vendor archive overlay order, exactly
                # as extracting them into one shared addon directory does.
                # Architecture packages intentionally share support filenames.
                if checksum is not None:
                    hashes[name] = checksum
                else:
                    hashes.pop(name, None)
                target = copy.copy(entry)
                target.name = name
                target.uid = target.gid = target.mtime = 0
                target.uname = target.gname = ''
                target.pax_headers = {}
                if entry.islnk():
                    target.linkname = prefix+member_name(entry.linkname)
                elif entry.issym():
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(original), entry.linkname))
                    if resolved.startswith('../') or entry.linkname.startswith('/') or '\\' in entry.linkname or ':' in entry.linkname:
                        raise ValueError('Addon link escapes its install directory')
                members[name] = archive, entry, target
        components = []
        for group, members in sorted(groups.items()):
            if group == 'mono':
                roots = {name.split('/')[4] for name in members}
                if len(roots) != 1:
                    raise ValueError('Mono vendor archives have incompatible root directories')
                alias = tarfile.TarInfo('files/share/wine/mono/wine-mono')
                alias.type, alias.mode, alias.linkname = tarfile.SYMTYPE, 0o777, next(iter(roots))
                if alias.name not in members:
                    members[alias.name] = None, None, alias
            pending = output/(group+'.tar.gz.part')
            with pending.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', compresslevel=1, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode='w|') as target:
                    for name in sorted(members):
                        archive, original, entry = members[name]
                        if entry.isfile():
                            with archive.extractfile(original) as source:
                                target.addfile(entry, source)
                        else:
                            target.addfile(entry)
            checksum = sha256_file(pending)
            name = 'wine-addons-'+group+'-'+checksum+'.tar.gz'
            pending.replace(output/name)
            components.append(dict(name='wine-addons-'+group, file=name, sha256=checksum,
                                   bytes=(output/name).stat().st_size, url=COMPONENT_BASE+name))
    metadata = dict(protocol=1, libc='bionic', files=dict(sorted(hashes.items())), originalSources={}, vendorDownloads=vendors)
    index = dict(format=1, kind='arlinux-bionic-components', runtime=metadata, components=components, sources=[])
    manifest = output/'arlinux-wine-addons.json'
    manifest.write_text(json.dumps(index, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')
    record = dict(request, outputIdentity=sha256_file(manifest))
    publish_distribution(request, record, output, repository=repository, index_name=manifest.name)
