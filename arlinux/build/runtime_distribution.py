"""Content-addressed Bionic runtime components, produced only by the final graph stage."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import tarfile

COMPONENT_TAG = 'arlinux-wine-components'
COMPONENT_BASE = 'https://github.com/taowen/wine/releases/download/'+COMPONENT_TAG+'/'
INDEX = 'arlinux-wine-runtime.json'


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def component_name(name):
    """Partition actual output paths, not a list of required DLLs/features."""
    path = Path(name)
    if 'fex' in path.name.lower():
        return 'fex'
    for prefix, group in (
        ('files/lib/arlinux/', 'integration'),
        ('files/share/arlinux/fonts/', 'fonts'),
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
    components = []
    for group, paths in sorted(groups.items()):
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
        components.append(dict(name=group, file=name, sha256=checksum,
                               bytes=archive.stat().st_size, url=COMPONENT_BASE+name))
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
