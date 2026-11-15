#!/usr/bin/env python3
"""Prepare and verify same-build APK libraries; never initiates a firmware build."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
ARCH='aarch64_cortex-a55_neon-vfpv4'
META='usr/share/mt6990-apk'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def readjson(path):return json.loads(path.read_text())
def writejson(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def flags(path):return dict(re.findall(r'^CONFIG_(\w[\w.-]*)=(.*)$',path.read_text(),re.M))
def command(args,**kwargs):return subprocess.run([str(a) for a in args],check=True,**kwargs)
def checked_identity(repo,snapshot,source):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid GitHub repository')
    if not re.fullmatch(r'[0-9]+-[0-9]+',snapshot):raise ValueError('Snapshot must be RUN_ID-RUN_ATTEMPT')
    if not re.fullmatch(r'[0-9a-f]{40}',source):raise ValueError('Invalid source commit')

def requested(profile):
    if profile.get('version')!=1:raise ValueError('Unsupported extra package profile')
    names=list(profile['utilities'])+list(profile['applications'])
    names += ['luci-i18n-'+p.removeprefix('luci-app-')+'-zh-cn' for p in profile['applications']]
    if len(names)!=len(set(names)) or not all(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9+_.-]*',p) for p in names):raise ValueError('Invalid/duplicate package name')
    return names

def select(root,config,profile_path):
    before=flags(config);text=config.read_text();selection={}
    for name in requested(readjson(profile_path)):
        symbol='PACKAGE_'+name
        # Existing built-ins keep y. New apps/tools remain installable-only m.
        value='y' if before.get(symbol)=='y' else 'm';selection[name]=value
        text=re.sub(r'^(CONFIG_'+re.escape(symbol)+r'=.*|# CONFIG_'+re.escape(symbol)+r' is not set)\n?', '',text,flags=re.M)
        text+=f'CONFIG_{symbol}={value}\n'
    config.write_text(text)
    writejson(root/'files'/META/'selection.json',selection)
    return selection

def verify_selection(root,config):
    expected=readjson(root/'files'/META/'selection.json');actual=flags(config)
    wrong=[p for p,v in expected.items() if actual.get('PACKAGE_'+p)!=v]
    if wrong:raise ValueError('Extra APK selections changed or disappeared after defconfig: '+', '.join(wrong))
    if any(actual.get(k)!='y' for k in ['SIGNED_PACKAGES','SIGN_EACH_PACKAGE','SIGNATURE_CHECK','USE_APK']):raise ValueError('APK package and index signing must remain enabled')
    if any(actual.get(k)!='y' for k in ['TARGET_mediatek_mt6990','TARGET_mediatek_mt6990_DEVICE_fiberhome_lg6851f']):raise ValueError('Only the LG6851F MT6990 target can publish this library')
    if actual.get('PACKAGE_python3-ctypes') in ('y','m') and actual.get('PACKAGE_libffi') not in ('y','m'):
        raise ValueError('python3-ctypes requires the target libffi provider; check recipe/index generation')
    if actual.get('TARGET_ARCH_PACKAGES')!='"'+ARCH+'"':raise ValueError('Wrong target package architecture')
    return expected

def prepare(root,repo,snapshot,source):
    checked_identity(repo,snapshot,source)
    actual=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if actual!=source:raise ValueError('Checkout SHA does not match requested build source')
    folder=root/'files'/META;folder.mkdir(parents=True,exist_ok=True)
    url=f'https://raw.githubusercontent.com/{repo}/apk-lib-{snapshot}/{snapshot}/packages.adb'
    (folder/'repositories.list').write_text(url+'\n')
    writejson(folder/'build.json',dict(version=1,artifact_tag='apk-lib-'+snapshot,board='fiberhome,lg6851f',target='mediatek/mt6990',source_sha=source,snapshot=snapshot,repository=repo,architecture=ARCH,repository_url=url))
    # These are legacy generated overlays, not the new immutable template.
    old=root/'files/etc/apk/repositories.d/nikki.list'
    if old.exists():old.unlink()

def collect_packages(root):
    directories=[root/'bin/targets/mediatek/mt6990/packages']
    directories+=sorted((root/'bin/packages'/ARCH).glob('*'))
    result={}
    for directory in directories:
        if not directory.is_dir():continue
        for path in sorted(directory.glob('*.apk')):
            if not path.resolve().is_relative_to((root/'bin').resolve()):raise ValueError('APK link escapes build output')
            if path.stat().st_size>=95*1024*1024:raise ValueError('APK exceeds GitHub file budget: '+path.name)
            if path.name in result and sha(path)!=sha(result[path.name]):raise ValueError('Conflicting duplicate APK filename: '+path.name)
            result[path.name]=path
    if not result:raise ValueError('No compiled APKs found')
    return result

def bundle(root,out,rootfs,apk):
    selection=verify_selection(root,root/'.config');meta=readjson(root/'files'/META/'build.json')
    checked_identity(meta['repository'],meta['snapshot'],meta['source_sha'])
    expected_url=f'https://raw.githubusercontent.com/{meta["repository"]}/apk-lib-{meta["snapshot"]}/{meta["snapshot"]}/packages.adb'
    if meta.get('version')!=1 or meta.get('board')!='fiberhome,lg6851f' or meta.get('target')!='mediatek/mt6990' or meta.get('architecture')!=ARCH or meta.get('repository_url')!=expected_url or (root/'files'/META/'repositories.list').read_text()!=expected_url+'\n':raise ValueError('Invalid build library identity or URL')
    if not out.resolve().is_relative_to((root/'bin').resolve()):raise ValueError('Repository output must be inside bin/')
    key=root/'public-key.pem';secret=root/'private-key.pem'
    if not key.is_file() or not secret.is_file():raise ValueError('Current build APK signing keys are missing')
    if (rootfs/'etc/apk/keys/public-key.pem').read_bytes()!=key.read_bytes():raise ValueError('Image APK public key differs from library key')
    for name in ['build.json','selection.json','repositories.list']:
        if (rootfs/META/name).read_bytes()!=(root/'files'/META/name).read_bytes():raise ValueError('Image feed identity differs from library: '+name)
    if (rootfs/META/'public-key.pem').read_bytes()!=key.read_bytes():raise ValueError('Read-only image library key differs from signing key')
    packages=collect_packages(root)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.apk-library-',dir=out.parent) as work:
        work=pathlib.Path(work);keys=work/'keys';keys.mkdir();shutil.copy2(key,keys/'public-key.pem')
        dest=work/'publish';dest.mkdir()
        for name,source in packages.items():shutil.copy2(source,dest/name)
        paths=sorted(dest.glob('*.apk'))
        # Bound batches: apk verify returns a failure count; never let 256 wrap to 0.
        for i in range(0,len(paths),32):command([apk,'--keys-dir',keys,'verify',*paths[i:i+32]])
        command([apk,'--keys-dir',keys,'mkndx','--sign',secret,'--output',dest/'packages.adb',*paths])
        command([apk,'--keys-dir',keys,'verify',dest/'packages.adb'])
        data=json.loads(subprocess.check_output([str(apk),'adbdump','--format','json',str(dest/'packages.adb')],text=True))
        rows=data['packages'];versions={row['name']:row['version'] for row in rows}
        if len(rows)!=len(paths) or len(versions)!=len(rows):raise ValueError('Index package count or duplicate package versions are invalid')
        if any(row.get('arch') not in [ARCH,'all','noarch'] for row in rows):raise ValueError('Foreign APK architecture in build output')
        optional={'nikki','luci-app-nikki','luci-i18n-nikki-zh-cn','mihomo-meta'}
        missing=(set(selection)|optional)-set(versions)
        # ABI suffixes apply to libraries, not the selected apps/tools in this profile.
        if missing:raise ValueError('Requested APK artifacts are missing: '+', '.join(sorted(missing)))
        if 'kernel' not in versions:raise ValueError('Kernel APK/ABI metadata is missing')
        if not re.match(r'^6\.18\.44([~+._-]|$)',versions['kernel']):raise ValueError('Unexpected kernel package version')
        with tempfile.TemporaryDirectory(prefix='apk-resolver-') as state:
            state=pathlib.Path(state);(state/'root').mkdir();repos=state/'repos.list';repos.write_text(str(dest/'packages.adb')+'\n')
            common=[apk,'--root',state/'root','--arch',ARCH,'--keys-dir',keys,'--no-network','--no-scripts']
            # A simulation cannot initialize a nonexistent APK database.
            command(common+['--repositories-file','/dev/null','add','--initdb','--usermode'])
            # Check every published package, including transitive libraries and
            # optional Nikki, independently. Repositories may contain alternatives
            # that are not meant to be installed together.
            for name in sorted(versions):
                try:
                    command(common+['--repositories-file',repos,'add','--usermode','--simulate',name],capture_output=True,text=True)
                except subprocess.CalledProcessError as error:
                    raise RuntimeError('APK dependency closure failed for '+name+': '+error.stderr) from error
        shutil.copy2(key,dest/'public-key.pem')
        for name in ['selection.json','build.json']:shutil.copy2(root/'files'/META/name,dest/name)
        plugins=root/'files/etc/mt6990-plugin-versions.json'
        if not plugins.is_file():raise ValueError('Actual upstream plugin/feed versions are missing')
        shutil.copy2(plugins,dest/'PLUGIN_VERSIONS.json')
        manifest={**meta,'config_sha256':sha(root/'.config'),'selection_sha256':sha(root/'files'/META/'selection.json'),'apk_tools':subprocess.check_output([str(apk),'--version'],text=True).strip(),'public_key_sha256':sha(key),'kernel_package':versions['kernel'],
                  'package_count':len(paths),'dependency_checked_packages':len(versions),'requested_packages':selection,'packages':versions,'plugins_sha256':sha(plugins)}
        writejson(dest/'repository.manifest.json',manifest)
        sums=''.join(sha(p)+'  '+p.name+'\n' for p in sorted(dest.iterdir()) if p.is_file())
        (dest/'SHA256SUMS').write_text(sums)
        # Immutable local outputs too: retries must reproduce byte-identical snapshots.
        if out.exists():
            if tree_hashes(out)!=tree_hashes(dest):raise ValueError('Refusing to replace an existing different library')
        else:shutil.move(str(dest),out)
    print(json.dumps({'snapshot':meta['snapshot'],'package_count':len(packages),'output':str(out)},ensure_ascii=False))

def tree_hashes(folder):
    if any(p.is_symlink() or not p.is_file() for p in folder.iterdir()):raise ValueError('Unexpected directory or link in published library')
    return {p.name:sha(p) for p in folder.iterdir()}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=pathlib.Path,default=ROOT)
    sub=parser.add_subparsers(dest='command',required=True)
    s=sub.add_parser('select');s.add_argument('--config',type=pathlib.Path);s.add_argument('--profile',type=pathlib.Path)
    s=sub.add_parser('prepare');s.add_argument('--repository',required=True);s.add_argument('--snapshot',required=True);s.add_argument('--source',required=True)
    sub.add_parser('verify-selection')
    s=sub.add_parser('bundle');s.add_argument('--output',type=pathlib.Path);s.add_argument('--rootfs',type=pathlib.Path,required=True);s.add_argument('--apk',type=pathlib.Path)
    a=parser.parse_args();root=a.root.resolve()
    if a.command=='select':select(root,a.config or root/'.config',a.profile or root/'config/mt6990-apk-extras.json')
    elif a.command=='prepare':prepare(root,a.repository,a.snapshot,a.source)
    elif a.command=='verify-selection':verify_selection(root,root/'.config')
    else:bundle(root,a.output or root/'bin/mt6990-apk-repository',a.rootfs,a.apk or root/'staging_dir/host/bin/apk')
if __name__=='__main__':main()
