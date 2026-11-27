#!/usr/bin/env python3
"""Append a verified library snapshot to the selected APK branch."""
import argparse
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('library',ROOT/'scripts/mt6990-apk-library.py');lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
APK_BRANCHES=('firmware-apk','firmware-apk-stock-accel-port')

def git(root,*args,**kwargs):return subprocess.run(['git','-C',str(root),*map(str,args)],check=True,**kwargs)

def publish(root,library,branch=APK_BRANCHES[0]):
    if branch not in APK_BRANCHES:raise ValueError('Unsupported firmware APK branch')
    branch_ref='refs/heads/'+branch
    manifest=lib.readjson(library/'repository.manifest.json');snapshot=manifest['snapshot']
    lib.checked_identity(manifest['repository'],snapshot,manifest['source_sha'])
    current=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if current!=manifest['source_sha']:raise ValueError('Publisher checkout differs from built source')
    expected={}
    for line in (library/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1)
        if pathlib.PurePath(name).name!=name:raise ValueError('Invalid library manifest path')
        expected[name]=digest
    hashes=lib.tree_hashes(library);hashes.pop('SHA256SUMS')
    if hashes!=expected:raise ValueError('Library manifest hashes do not match files')
    if any(p.name.endswith('private-key.pem') for p in library.iterdir()):raise ValueError('Private key in publish directory')
    status=subprocess.run(['git','-C',str(root),'ls-remote','--exit-code','origin',branch_ref],capture_output=True,text=True)
    if status.returncode not in [0,2]:raise RuntimeError('Cannot inspect library branch: '+status.stderr)
    tag='apk-lib-'+snapshot
    existing_tag=subprocess.run(['git','-C',str(root),'ls-remote','--exit-code','origin','refs/tags/'+tag],capture_output=True,text=True)
    if existing_tag.returncode not in [0,2]:raise RuntimeError('Cannot inspect immutable library tag')
    origin=subprocess.check_output(['git','-C',str(root),'remote','get-url','origin'],text=True).strip()
    # Work in an isolated sparse repository. Old snapshot blobs stay remote,
    # rather than downloading every previous library on each firmware build.
    with tempfile.TemporaryDirectory(prefix='mt6990-apk-publish-') as temporary:
        work=pathlib.Path(temporary)/'tree';work.mkdir()
        git(work,'init','--quiet')
        git(work,'config','credential.helper','!gh auth git-credential')
        git(work,'remote','add','origin',origin)
        git(work,'config','user.name','github-actions[bot]');git(work,'config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
        if status.returncode==0:
            git(work,'config','remote.origin.promisor','true')
            git(work,'config','remote.origin.partialclonefilter','blob:none')
            git(work,'fetch','--depth=1','--filter=blob:none','origin',branch_ref)
            git(work,'sparse-checkout','init','--no-cone')
            git(work,'sparse-checkout','set','--no-cone','/README.md','/'+snapshot+'/')
            git(work,'checkout','--detach','FETCH_HEAD')
        dest=work/snapshot
        if dest.exists():
            if lib.tree_hashes(dest)!=lib.tree_hashes(library):raise ValueError('Immutable snapshot already exists with different bytes')
            if existing_tag.returncode==0:
                git(work,'fetch','--depth=1','--filter=blob:none','origin','refs/tags/'+tag)
                tagged=git(work,'rev-parse','FETCH_HEAD:'+snapshot,text=True,capture_output=True).stdout.strip()
                current=git(work,'rev-parse','HEAD:'+snapshot,text=True,capture_output=True).stdout.strip()
                if tagged!=current:raise ValueError('Immutable tag points to different library bytes')
            else:
                git(work,'push','--atomic','origin','HEAD:'+branch_ref,'HEAD:refs/tags/'+tag)
            print('APK_LIBRARY_ALREADY_PUBLISHED='+snapshot);return
        if existing_tag.returncode==0:raise ValueError('Immutable tag exists but snapshot is missing from branch')
        shutil.copytree(library,dest)
        (work/'README.md').write_text('# LG6851F same-build APK snapshots\n\nEach RUN_ID-RUN_ATTEMPT directory belongs only to its matching firmware.\nSnapshots are append-only. Never add these feeds to other firmware versions.\n')
        git(work,'add',snapshot,'README.md')
        git(work,'commit','-m',f'Publish firmware APK library {snapshot} from {manifest["source_sha"]}')
        # No force-push: concurrent changes must fail for a fresh recheck.
        git(work,'push','--atomic','origin','HEAD:'+branch_ref,'HEAD:refs/tags/'+tag)
    print('APK_LIBRARY_PUBLISHED='+snapshot)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=pathlib.Path,default=ROOT);p.add_argument('--library',type=pathlib.Path);p.add_argument('--branch',choices=APK_BRANCHES,default=APK_BRANCHES[0]);a=p.parse_args()
    publish(a.root.resolve(),a.library or a.root/'bin/mt6990-apk-repository',a.branch)
if __name__=='__main__':main()
