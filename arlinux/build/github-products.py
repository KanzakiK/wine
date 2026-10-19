#!/usr/bin/env python3
"""Dispatch independent repository workflows from Windows or Linux, without WSL."""
import argparse
from contextlib import contextmanager
import errno
import os
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from threading import Event
from artifact_download import download,sha256_file,reuse_product,download_capsule
from component_inputs import request_identity, source_inputs


def gh(*args, optional=False):
    attempts=4 if args[0] in ('api','run') else 1
    for attempt in range(attempts):
        result = subprocess.run(['gh', *map(str,args)], capture_output=True, text=True)
        if not result.returncode or not any(message in result.stderr.lower() for message in
                ('timeout','timed out','connection','eof','502','503','504','tls handshake')):
            break
        if attempt+1<attempts:
            time.sleep(2**attempt)
    if result.returncode:
        if optional and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def api(path, optional=False):
    value = gh('api', path, optional=optional)
    return json.loads(value) if value else None


@contextmanager
def request_lock(path, stopped):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as lock:
        if not path.stat().st_size:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 8*60*60
        while True:
            try:
                lock.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if stopped.wait(0.25):
                    raise RuntimeError('Local coordinator stopped while waiting for a component')
                if time.monotonic() > deadline:
                    raise TimeoutError('Timed out waiting for component request lock')
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


class Coordinator:
    def __init__(self, plan, framework, android, state, poll=30):
        self.plan,self.framework,self.android,self.state,self.poll = plan,framework,android,state,poll
        state.mkdir(parents=True,exist_ok=True)
        self.stopped = Event()
        self.timings = {}
        self.local_manifests = set()

    def runs(self, repository):
        return json.loads(gh('run','list','--repo',repository,'--workflow',self.plan['workflow'],
            '--limit','100','--json','databaseId,displayTitle,status,conclusion,url'))

    def existing(self, request):
        repository = self.plan['stages'][request['stage']]['repository']
        tag = 'arlinux-'+request['stage']+'-'+request['identity'][:24]
        directory = self.state/request['identity']
        manifest = directory/'component.json'
        reference_file = directory/'reference.json'
        url = f'https://github.com/{repository}/releases/download/{tag}/component.json'
        def validate(record):
            for name in ('stage','identity','android','dependencies', 'sourceInputs'):
                if record.get(name) != request.get(name):
                    raise ValueError('Component release differs from the requested inputs: '+name)
        # Only immutable, checksum-bound completion records are reusable here.
        # Mutable latest selections deliberately never use this cache.
        try:
            reference = json.loads(reference_file.read_text())
            if (set(reference) != {'repository','identity','manifestUrl','manifestSha256'}
                    or reference['repository'] != repository or reference['identity'] != request['identity']
                    or reference['manifestUrl'] != url
                    or not re.fullmatch('[0-9a-f]{64}', reference['manifestSha256'])
                    or sha256_file(manifest) != reference['manifestSha256']):
                raise ValueError('Invalid cached component reference')
            validate(json.loads(manifest.read_text()))
            self.local_manifests.add(request['stage'])
            return reference
        except (OSError, ValueError, KeyError, TypeError):
            pass
        release = api(f'repos/{repository}/releases/tags/{tag}',optional=True)
        if not release:
            return None
        asset = next((a for a in release['assets'] if a['name']=='component.json'),None)
        if not asset:
            return None
        digest = asset.get('digest','')
        if not digest.startswith('sha256:'):
            raise ValueError('GitHub did not supply the component manifest SHA-256')
        download(asset['browser_download_url'],manifest,digest[7:])
        record = json.loads(manifest.read_text())
        validate(record)
        names={a['name'] for a in release['assets']}
        if any(part['name'] not in names for part in record['parts']):
            return None
        reference = dict(repository=repository,identity=request['identity'],
            manifestUrl=asset['browser_download_url'],manifestSha256=digest[7:])
        if reference['manifestUrl'] != url:
            raise ValueError('Unexpected immutable component manifest URL')
        pending = reference_file.with_suffix('.tmp')
        pending.write_text(json.dumps(reference, sort_keys=True)+'\n')
        pending.replace(reference_file)
        return reference

    def component(self, stage, dependencies):
        started = time.monotonic()
        framework = Path(__file__).resolve().parents[2]
        request = dict(format=2,stage=stage,framework=self.framework,android=self.android,
                       dependencies=dependencies, sourceInputs=source_inputs(framework, self.framework, stage, self.plan))
        request['identity']=request_identity(request)
        with request_lock(self.state/request['identity']/'dispatch.lock', self.stopped):
            result = self._component(request)
        self.timings[stage] = dict(seconds=round(time.monotonic()-started, 3),
                                  repository=result['repository'], identity=result['identity'],
                                  manifestSource='local' if stage in self.local_manifests else 'github')
        return result

    def _component(self, request):
        stage = request['stage']
        repository=self.plan['stages'][stage]['repository']
        result=self.existing(request)
        if result:
            print('OK published '+repository+'/'+stage,flush=True)
            return result
        payload=json.dumps(request,sort_keys=True)
        # A standalone workflow_dispatch creates a run in the component repo.
        # Do not replace this with workflow_call: caches must belong to that repo.
        title='arlinux/'+stage+'/'+request['identity']
        previous_runs=self.runs(repository)
        run=next((r for r in previous_runs if r['displayTitle']==title and r['status']!='completed'),None)
        ignored={r['databaseId'] for r in previous_runs if r['status']=='completed'}
        if not run:
            # Capsules contain verified build receipts, including references.
            # They can seed a new run after an unrelated framework commit; the
            # producer's input hashes, not this coordinator, decide cache hits.
            if stage not in ('yibu','debian','arch','omarchy','plasma','lxqt','windows-fonts','wine-product'):
                releases=api(f'repos/{repository}/releases?per_page=100')
                candidate=next((r for r in releases if re.fullmatch(re.escape('arlinux-'+stage+'-')+'[0-9a-f]{24}',r['tag_name']) and
                                any(a['name']=='component.json' for a in r['assets'])),None)
                if candidate:
                    asset=next(a for a in candidate['assets'] if a['name']=='component.json')
                    digest=asset.get('digest','')
                    if digest.startswith('sha256:'):
                        request['cacheSeed']=dict(repository=repository,
                            identity=candidate['tag_name'][len('arlinux-'+stage+'-'):],
                            manifestUrl=asset['browser_download_url'],manifestSha256=digest[7:])
                        # The tag contains a short identity; read the verified manifest.
                        file=self.state/request['identity']/'seed.json'
                        download(asset['browser_download_url'],file,digest[7:])
                        seed=json.loads(file.read_text())
                        if seed['stage']!=stage:
                            raise ValueError('Cache seed belongs to a different component')
                        request['cacheSeed']['identity']=seed['identity']
            payload=json.dumps(request,sort_keys=True)
            gh('workflow','run',self.plan['workflow'],'--repo',repository,'-f','request='+payload)
            print('START '+repository+'/'+stage,flush=True)
        else:
            print('RESUME '+repository+'/'+stage+' '+run['url'],flush=True)
        deadline=time.monotonic()+7*60*60
        previous=None
        while time.monotonic()<deadline:
            if self.stopped.is_set():
                raise RuntimeError('Local coordinator stopped; remote workflows remain available to resume')
            runs=self.runs(repository)
            matches=[r for r in runs if r['displayTitle']==title and r['databaseId'] not in ignored]
            run=next((r for r in matches if r['conclusion']=='success'),
                     next((r for r in matches if r['status']!='completed'), matches[0] if matches else None))
            if run:
                status=run['status']+'/'+str(run['conclusion'])
                if status!=previous:
                    print(stage+': '+status+' '+run['url'],flush=True)
                    previous=status
                if run['status'] != 'queued':
                    result = self.existing(request)
                    if result:
                        print('OK verified publication '+repository+'/'+stage+
                              '; workflow cache cleanup may still be running', flush=True)
                        return result
                if run['status']=='completed':
                    if run['conclusion']!='success':
                        raise RuntimeError(stage+' failed: '+run['url'])
                    result=self.existing(request)
                    if not result:
                        raise ValueError('Successful workflow did not publish its verified capsule')
                    return result
            self.stopped.wait(self.poll)
        raise TimeoutError('Component workflow timed out: '+stage)

    def run(self, products, parallel):
        required=set()
        def visit(stage):
            if stage in required:
                return
            for dependency in self.plan['stages'][stage]['dependencies']:
                visit(dependency)
            required.add(stage)
        for product in products:
            visit(self.plan['products'][product])
        completed={}
        pending=set(required)
        active={}
        consumers = {name: [] for name in required}
        for name in required:
            for dependency in self.plan['stages'][name]['dependencies']:
                consumers[dependency].append(name)
        ranks = {}
        def rank(name):
            if name not in ranks:
                ranks[name] = 1 + max((rank(child) for child in consumers[name]), default=0)
            return ranks[name]
        for name in required:
            rank(name)
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            while pending or active:
                for stage in sorted(pending, key=lambda name: (-ranks[name], name)):
                    dependencies=self.plan['stages'][stage]['dependencies']
                    if all(name in completed for name in dependencies) and len(active)<parallel:
                        future=executor.submit(self.component,stage,[completed[n] for n in dependencies])
                        active[future]=stage
                        pending.remove(stage)
                if not active:
                    raise ValueError('Component dependency graph contains a cycle')
                done,_=wait(active,return_when=FIRST_COMPLETED)
                for future in done:
                    stage=active.pop(future)
                    try:
                        completed[stage]=future.result()
                    except BaseException:
                        self.stopped.set()
                        raise
                    (self.state/'progress.json').write_text(json.dumps(completed,indent=2)+'\n')
        return {product:completed[self.plan['products'][product]] for product in products}


def fetch_product(reference, output):
    identity = reference['identity']
    if not re.fullmatch('[0-9a-f]{64}', identity):
        raise ValueError('Invalid product component identity')
    directory = output.parent/'github-state/downloads'/identity
    with request_lock(directory/'transfer.lock', Event()):
        if reuse_product(output, reference):
            return
        cache_receipt=output/'download-receipt.json'
        import zstandard
        manifest=directory/'component.json'
        download(reference['manifestUrl'],manifest,reference['manifestSha256'])
        record=json.loads(manifest.read_text())
        if record['identity']!=reference['identity']:
            raise ValueError('Product identity mismatch')
        if record.get('artifacts'):
            # Device testing needs only the runtime. Source archives are fetched
            # by the publisher on demand, using the same verified component record.
            output.mkdir(parents=True, exist_ok=True)
            files = {}
            object_cache = directory.parent/'objects'
            def fetch_artifact(item):
                name = item['name']
                if Path(name).name != name or '\\' in name or ':' in name:
                    raise ValueError('Unsafe product artifact name')
                with request_lock(object_cache/(item['sha256']+'.lock'), Event()):
                    cached = download(item['url'], object_cache/item['sha256'], item['sha256'], label=name)
                if cached.stat().st_size != item['bytes']:
                    raise ValueError('Product artifact size mismatch')
                import shutil
                shutil.copyfile(cached, output/name)
                return name, item['sha256']
            artifacts = [item for item in record['artifacts'] if item['role'] in ('runtime', 'manifest')]
            if len({item['name'] for item in artifacts}) != len(artifacts):
                raise ValueError('Duplicate product artifact name')
            with ThreadPoolExecutor(max_workers=4) as pool:
                files.update(pool.map(fetch_artifact, artifacts))
            from runtime_distribution import INDEX, read_index
            read_index(output/INDEX)
            (output/'github-component.json').write_text(json.dumps(record, indent=2)+'\n')
            files['github-component.json'] = sha256_file(output/'github-component.json')
            cache_receipt.write_text(json.dumps(dict(format=1, reference=reference, files=files), indent=2)+'\n')
            return
        archive=download_capsule(record, directory)
        audio=record['stage']=='wine-pulse'
        product=('audio' if audio else 'diagnostics' if record['stage']=='wine-diagnostics'
                 else 'wine-capture' if record['stage']=='wine-capture' else 'wine')
        prefix='framework/build/artifacts/'+product+'/'
        output.mkdir(parents=True,exist_ok=True)
        with archive.open('rb') as source,zstandard.ZstdDecompressor().stream_reader(source) as decoded:
            with tarfile.open(fileobj=decoded,mode='r|') as capsule:
                for member in capsule:
                    if not member.isfile():
                        continue
                    if audio:
                        if not member.name.startswith('framework/build/pipeline/wine-pulse/') or '/output/android/' not in member.name:
                            continue
                        name=member.name.split('/output/android/',1)[1]
                        if not name.startswith(('jni/arm64-v8a/','assets/pulseaudio/')):
                            raise ValueError('Unexpected audio output')
                    else:
                        if not member.name.startswith(prefix):
                            continue
                        name=member.name[len(prefix):]
                    if '\\' in name or ':' in name or any(p in ('','.','..') for p in name.split('/')) or (not audio and '/' in name):
                        raise ValueError('Unsafe product archive member')
                    (output/name).parent.mkdir(parents=True,exist_ok=True)
                    with (output/name).open('wb') as dest:
                        import shutil
                        shutil.copyfileobj(capsule.extractfile(member),dest)
        (output/'github-component.json').write_text(json.dumps(record,indent=2)+'\n')
        if audio:
            files={str(p.relative_to(output)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in ('jni','assets') for p in (output/folder).rglob('*') if p.is_file()}
            (output/'build-receipt.json').write_text(json.dumps(dict(format=1,component=reference,files=files),indent=2)+'\n')
        elif product=='wine':
            archive=output/'arlinux-wine-bionic.tar.gz'
            with archive.open('rb') as source:
                digest=hashlib.file_digest(source,'sha256').hexdigest()
            expected=(output/(archive.name+'.sha256')).read_text().split()[0]
            if digest!=expected:
                raise ValueError('Wine checksum does not match the downloaded product')
        files={p.relative_to(output).as_posix():sha256_file(p)
               for p in output.rglob('*') if p.is_file() and p!=cache_receipt}
        cache_receipt.write_text(json.dumps(dict(format=1,reference=reference,files=files),indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework-ref',default='arlinux')
    parser.add_argument('--product',choices=('wine','audio','diagnostics','wine-capture','all'),default='all')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parallel',type=int,default=8)
    parser.add_argument('--plan',action='store_true')
    args=parser.parse_args()
    framework=Path(__file__).resolve().parents[2]
    plan=json.loads((framework/'arlinux/build/github-components.json').read_text())
    if args.plan:
        print(json.dumps(plan,indent=2))
        return
    framework_sha=(args.framework_ref if re.fullmatch('[0-9a-f]{40}',args.framework_ref)
                   else api('repos/taowen/wine/commits/'+args.framework_ref)['sha'])
    products=['wine','audio'] if args.product=='all' else [args.product]
    state=args.output/'github-state'
    coordinator=Coordinator(plan,framework_sha,None,state)
    started=time.monotonic()
    result=coordinator.run(products,args.parallel)
    graph_seconds=time.monotonic()-started
    transfers={}
    for name,reference in result.items():
        transfer_started=time.monotonic()
        fetch_product(reference,args.output/name)
        transfers[name]=dict(seconds=round(time.monotonic()-transfer_started,3))
    (args.output/('products-'+args.product+'.json')).write_text(json.dumps(dict(format=1,
        framework=framework_sha,products=result),indent=2)+'\n')
    (args.output/('build-timing-'+args.product+'.json')).write_text(json.dumps(dict(format=1,
        framework=framework_sha, totalSeconds=round(time.monotonic()-started,3),
        graphSeconds=round(graph_seconds,3), components=coordinator.timings,
        productTransfers=transfers),indent=2)+'\n')


if __name__=='__main__':
    main()
