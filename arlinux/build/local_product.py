"""Pin independently published runtime manifests; never unpack a capsule."""
import json
from artifact_download import download, sha256_file
from runtime_distribution import INDEX, publish_distribution


def build(request, directory, repository, object_cache):
    manifests = []
    for reference in request['dependencies']:
        source = download(reference['manifestUrl'], directory/'inputs'/reference['identity']/'component.json',
                          reference['manifestSha256'])
        record = json.loads(source.read_text())
        if record['identity'] != reference['identity']:
            raise ValueError('Runtime producer identity mismatch')
        manifest = record['runtimeManifest']
        if manifest['name'] != record['stage']:
            raise ValueError('Runtime manifest belongs to a different producer')
        manifests.append(manifest)
    output = directory/'product'
    output.mkdir(parents=True, exist_ok=True)
    catalog = dict(format=2, kind='arlinux-bionic-manifests', manifests=manifests)
    target = output/INDEX
    target.write_text(json.dumps(catalog, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')
    record = dict(request, outputIdentity=sha256_file(target))
    publish_distribution(request, record, output, repository=repository)
    object_cache.mkdir(parents=True, exist_ok=True)
    cached = object_cache/sha256_file(target)
    pending = cached.with_suffix('.local-part')
    pending.write_bytes(target.read_bytes())
    if sha256_file(pending) != record['outputIdentity']:
        raise ValueError('Runtime selection changed while caching')
    pending.replace(cached)
