#!/usr/bin/env python3
"""Resolve latest upstream plugins once per build, preserving local adaptations."""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'config/mt6990-plugin-upstreams.json'


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path]))


def archive(repo, sha, folder, subpaths=None):
    output = folder / (repo.replace('/', '-') + '-' + sha + '.tar.gz')
    if not output.exists():
        with output.open('wb') as stream:
            subprocess.run(['gh', 'api', f'repos/{repo}/tarball/{sha}'], stdout=stream, check=True)
    dest = folder / output.name.removesuffix('.tar.gz')
    if not dest.exists():
        dest.mkdir()
        with tarfile.open(output) as tar:
            selected=[]
            for entry in tar:
                parts=pathlib.PurePosixPath(entry.name).parts
                relative='/'.join(parts[1:])
                if subpaths and not any(relative==p or relative.startswith(p.rstrip('/')+'/') for p in subpaths):
                    continue
                selected.append(entry)
                path = pathlib.PurePosixPath(entry.name)
                if path.is_absolute() or '..' in path.parts or not (entry.isfile() or entry.isdir()):
                    raise RuntimeError(f'Unsupported archive entry: {entry.name}')
            tar.extractall(dest,members=selected)
    return next(dest.iterdir()), hashlib.sha256(output.read_bytes()).hexdigest()


def merge_file(local, base, upstream):
    """Three-way merge in memory. Never silently overwrite a local adaptation."""
    if local == base:
        return upstream
    if upstream == base or local == upstream:
        return local
    if local is None or base is None or upstream is None or any(b'\0' in x for x in [local, base, upstream]):
        raise RuntimeError('Conflicting added/deleted/binary file')
    with tempfile.TemporaryDirectory() as folder:
        files = [pathlib.Path(folder) / name for name in ['local', 'base', 'upstream']]
        for file, data in zip(files, [local, base, upstream]):
            file.write_bytes(data)
        result = subprocess.run(['git', 'merge-file', '-p', *map(str, files)], capture_output=True)
        if result.returncode:
            raise RuntimeError('Upstream change conflicts with MT6990 adaptation')
        return result.stdout


def file_bytes(path):
    return path.read_bytes() if path.is_file() else None


def adapt_uu_helpers(package):
    # Upstream relies on postinst chmod; our native source build must also
    # have executable helpers in the assembled rootfs, before first boot.
    for path in [package/'root/etc/init.d/uuplugin',*(package/'root/usr/libexec/uuplugin').rglob('*')]:
        if path.is_file():
            path.chmod(0o755)


def prepare_package(row, latest, folder):
    repo = row['repo']
    scopes=([row['path']]+row.get('source_helpers',[])) if row.get('path') else None
    base, _ = archive(repo, row['base'], folder,scopes)
    upstream, digest = archive(repo, latest, folder,scopes)
    base /= row.get('path', '')
    upstream /= row.get('path', '')
    local = ROOT / 'package/lg6851f' / row['package']
    if not local.is_dir():
        local = ROOT / 'package/vendor' / row['package']
    # All merges are checked before writing any package files.
    changes = []
    for component in row['components']:
        paths = set()
        for source in [base, upstream]:
            root = source / component
            if root.is_dir():
                paths.update(p.relative_to(source) for p in root.rglob('*') if p.is_file())
            elif root.is_file():
                paths.add(pathlib.Path(component))
        for path in sorted(paths):
            if str(path) in row.get('preserve', []):
                continue
            try:
                merged = merge_file(file_bytes(local / path), file_bytes(base / path), file_bytes(upstream / path))
            except RuntimeError as error:
                raise RuntimeError(f'{row["package"]}/{path}: {error}') from error
            changes.append((local / path, merged, (upstream / path).stat().st_mode if (upstream / path).exists() else None))
    for path, data, mode in changes:
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if mode is not None:
                path.chmod(mode & 0o777)
    # UU uses our native ARM64 build and nft provider dependencies. Only merge
    # additional upstream dependencies, not incompatible package provider names.
    if row.get('managed_makefile'):
        makefile = local / 'Makefile'
        old = makefile.read_text()
        new = (upstream / 'Makefile').read_text()
        version = re.search(r'^PKG_VERSION:=(.+)$', new, re.M).group(1)
        old = re.sub(r'^PKG_VERSION:=.*$', 'PKG_VERSION:=' + version, old, flags=re.M)
        if row['package'] == 'luci-app-uugamebooster':
            def deps(text):
                return set(re.search(r'^LUCI_DEPENDS:=(.*)$', text, re.M).group(1).split())
            added = deps(new) - deps((base / 'Makefile').read_text())
            old = re.sub(r'^LUCI_DEPENDS:=(.*)$', lambda m: m[0] + ''.join(' ' + d for d in sorted(added) if d not in m[1].split()), old, flags=re.M)
        makefile.write_text(old)
    # The package's standalone C helper lives above the upstream LuCI folder.
    if row.get('source_helpers'):
        for component in row['source_helpers']:
            b = base.parent / component
            u = upstream.parent / component
            for path in sorted(set(p.name for p in b.glob('*.c')) | set(p.name for p in u.glob('*.c'))):
                dst = local / 'src' / path
                merged = merge_file(file_bytes(dst), file_bytes(b / path), file_bytes(u / path))
                if merged is None:
                    dst.unlink(missing_ok=True)
                else:
                    dst.write_bytes(merged)
    if row['package']=='luci-app-uugamebooster':
        adapt_uu_helpers(local)
    row['base'] = latest
    return {'package': row['package'], 'repo': repo, 'commit': latest, 'archive_sha256': digest,
            'version': re.search(r'^PKG_VERSION:=(.+)$', (local / 'Makefile').read_text(), re.M).group(1) if re.search(r'^PKG_VERSION:=(.+)$', (local / 'Makefile').read_text(), re.M) else 'upstream-head'}


def smart_asset(release):
    if release.get('tag_name') != 'Prerelease-Alpha' or release.get('draft'):
        raise RuntimeError('Expected vernesong Smart Prerelease-Alpha release')
    assets=[a for a in release['assets'] if re.fullmatch(r'mihomo-linux-arm64-alpha-smart-[0-9a-f]{7,40}\.gz',a['name'])]
    if len(assets)!=1:raise RuntimeError('Expected exactly one ARM64 Smart alpha asset')
    asset=assets[0]
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',asset.get('digest','')):raise RuntimeError('Smart alpha asset has no official SHA256 digest')
    try:
        stamp=datetime.datetime.strptime(asset.get('updated_at',''),'%Y-%m-%dT%H:%M:%SZ')
    except ValueError as error:
        raise RuntimeError('Smart alpha asset timestamp is invalid') from error
    upstream=asset['name'].removeprefix('mihomo-linux-arm64-').removesuffix('.gz')
    # APK uses numeric release components and _alpha suffixes, not arbitrary
    # ~alpha.smart.HASH strings. Keep the exact hash in PKG_UPSTREAM_VERSION.
    return asset, stamp.strftime('%Y%m%d.%H%M%S')+'_alpha0',upstream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-only', action='store_true', help='report the fixed checkout without updating plugins')
    args = parser.parse_args()
    rows = json.loads(REGISTRY.read_text())
    if args.report_only:
        checkout = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        records = [{'package': row['package'], 'repo': row['repo'], 'upstream_base': row['base'],
                    'source_sha': checkout} for row in rows]
    else:
        records = []
        with tempfile.TemporaryDirectory(prefix='mt6990-plugin-update-') as folder:
            folder = pathlib.Path(folder)
            for row in rows:
                if row.get('branch'):
                    latest = api(f'repos/{row["repo"]}/commits/{row["branch"]}')['sha']
                else:
                    release = api(f'repos/{row["repo"]}/releases/latest')
                    if release['draft'] or release['prerelease']:
                        raise RuntimeError('Latest stable release was not returned')
                    latest = api(f'repos/{row["repo"]}/commits/{release["tag_name"]}')['sha']
                records.append(prepare_package(row, latest, folder))
                REGISTRY.write_text(json.dumps(rows, indent=2) + "\n")
    # The Pro port keeps these vendor package recipes at the imported revision.
    pinned = ['luci-app-openclash', 'mihomo-openclash-core']
    if args.report_only:
        pinned += ['nikki', 'luci-app-nikki', 'luci-i18n-nikki-zh-cn', 'mihomo-meta']
    for package in pinned:
        recipe = (ROOT/'package/vendor'/package/'Makefile').read_text()
        version = re.search(r'^PKG_VERSION:=(.+)$', recipe, re.M)
        if not version:
            raise RuntimeError(f'{package}: missing pinned version')
        records.append({'package': package, 'repo': 'adian2020/LG6851F-Pro',
                        'commit': '0e1518ed632388e814032e0831560d22d9488981',
                        'version': version[1]})
    configured=set(re.findall(r'^src-(?:git|link)\s+(\S+)',(ROOT/'feeds.conf.default').read_text(),re.M))
    for feed in sorted((ROOT / 'feeds').iterdir()):
        if feed.name in configured and (feed / '.git').exists():
            records.append({'feed': feed.name, 'commit': subprocess.check_output(['git', '-C', str(feed), 'rev-parse', 'HEAD'], text=True).strip()})
    report = ROOT / 'files/etc/mt6990-plugin-versions.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    if not args.report_only:
        REGISTRY.write_text(json.dumps(rows, indent=2) + '\n')
    print(report.read_text())


if __name__ == '__main__':
    main()
