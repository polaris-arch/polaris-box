#!/usr/bin/env python3
"""Review-gated production desktop release actions; never called by native CI.

Preparation is local only. No cleanup/overwrite, upstream writes, device changes,
mobile acceptance, signing assertion or automatic publication from build results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
sys.dont_write_bytecode = True
from polaris_production_release import basename, encode, file_info, frozen_source, require, sha

REPOSITORY = 'polaris-arch/polaris-box'
REPOSITORY_ID = 1407705262
APPROVAL_GATES = ('independentSourceReview', 'licenseSourceReview', 'AppOwnerSignoff')


def command(*args, data=None):
    return subprocess.check_output([str(x) for x in args], input=data).decode().strip()


def api(endpoint, payload=None):
    args = ['gh', 'api', '--method', 'GET', endpoint]
    if payload is not None:
        with tempfile.TemporaryDirectory(prefix='polaris-api-input-') as directory:
            path = Path(directory) / 'payload.json'
            path.write_bytes(encode(payload))
            return json.loads(command('gh', 'api', endpoint, '--method', 'POST', '--input', path))
    return json.loads(command(*args))


def annotation(head, tag, epoch, name, email):
    require(epoch.isdigit(), 'explicit UTC tag epoch required')
    require(name and email and not any(c in name + email for c in '\n\r\0<>'), 'invalid tagger identity')
    return (f'object {head}\ntype commit\ntag {tag}\ntagger {name} <{email}> {epoch} +0000\n\n'
            f'Polaris-box {tag[1:]} desktop CLI\nSource: {head}\n'
            'Six native desktop targets; mobile/final App acceptance is separate.\n').encode()


def tag_sha(data):
    return hashlib.sha1(b'tag ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def prepare(repo, expected, inputs, index_sha, approvals, approvals_sha, output, epoch, name, email):
    config, tree = frozen_source(repo, expected)
    require(not output.exists() and not output.resolve().is_relative_to(repo.resolve()), 'fresh external preparation required')
    raw = (inputs / 'polaris-box-assets.json').read_bytes()
    require(sha(raw) == index_sha, 'reviewed actual native index hash differs')
    index = json.loads(raw)
    require(index['sourceCommit'] == expected and index['sourceTree'] == tree
            and index['version'] == config['version'] and index['tag'] == config['tag']
            and index['repository'] == REPOSITORY and index['tagObject'] is None, 'actual assembly identity differs')
    require(len(index['platforms']) == 6 and {r['target'] for r in index['platforms']}
            == {r['target'] for r in config['desktop']}, 'actual six native receipts required')
    # A reviewed source commit alone is insufficient: reviewer approvals bind the
    # exact already-produced index and scope. This program cannot create approvals.
    approval_bytes = approvals.read_bytes()
    require(sha(approval_bytes) == approvals_sha, 'independently reviewed approvals hash differs')
    review = json.loads(approval_bytes)
    require(review['schema'] == 'polaris-production-approvals-v1' and review['sourceCommit'] == expected
            and review['version'] == config['version'] and review['nativeIndexSha256'] == index_sha
            and review['scope'] == 'six-desktop-CLI', 'approval scope/input differs')
    for gate in APPROVAL_GATES:
        require(review['gates'][gate]['status'] == 'approved' and review['gates'][gate]['reviewer']
                and review['gates'][gate]['evidence'], 'missing actual approval: ' + gate)
    require(index['workflowRun'] and index['workflowAttempt'], 'actual native run identity required')
    specifications = {r['target']: r for r in config['desktop']}
    for row in index['platforms']:
        require(row['archive']['name'] == basename(config, row['target']) + specifications[row['target']]['suffix'], 'native archive name differs')
    require(index['sourceAsset']['name'] == 'polaris-box-' + config['version'] + '-source.tar.gz', 'standalone source name differs')
    expected_archives = {r['archive']['name']: r['archive'] for r in index['platforms']}
    expected_archives[index['sourceAsset']['name']] = index['sourceAsset']
    require(len(expected_archives) == 7, 'exact six native archives and standalone source required')
    require(all(p.is_file() and not p.is_symlink() for p in inputs.iterdir()), 'regular immutable assembly inputs required')
    for record in expected_archives.values():
        require(file_info(inputs / record['name']) == {k: record[k] for k in ('name', 'bytes', 'sha256')}, 'actual assembly bytes differ')
    expected_names = set(expected_archives) | {'polaris-box-assets.json', 'SHA256SUMS'}
    require({p.name for p in inputs.iterdir()} == expected_names, 'exact nine assembled inputs required')
    expected_sums = ''.join(f"{file_info(inputs / n)['sha256']}  {n}\n" for n in sorted(expected_names - {'SHA256SUMS'}))
    require((inputs / 'SHA256SUMS').read_text() == expected_sums, 'actual assembled checksums differ')
    tag_bytes = annotation(expected, config['tag'], epoch, name, email)
    object_sha = tag_sha(tag_bytes)
    output.mkdir(parents=True)
    for n in sorted(expected_archives):
        shutil.copyfile(inputs / n, output / n)
    index['tagObject'] = object_sha
    index['tagObjectState'] = 'prepared-expectation; remote tag creation and verification pending'
    index['publicationEligible'] = True
    for gate in APPROVAL_GATES:
        index['gates'][gate] = review['gates'][gate]
    # Public download and final App/device/mobile proof remain pending.
    (output / 'polaris-box-assets.json').write_bytes(encode(index))
    names = set(expected_archives) | {'polaris-box-assets.json'}
    (output / 'SHA256SUMS').write_text(''.join(f"{file_info(output / n)['sha256']}  {n}\n" for n in sorted(names)))
    assets = [file_info(output / n) for n in sorted(names | {'SHA256SUMS'})]
    manifest = {'schema': 'polaris-production-publication-v1', 'repository': REPOSITORY, 'repositoryId': REPOSITORY_ID,
        'sourceCommit': expected, 'sourceTree': tree, 'version': config['version'], 'tag': config['tag'],
        'tagObject': object_sha, 'tagObjectBytesHex': tag_bytes.hex(), 'assets': assets,
        'title': 'Polaris-box ' + config['version'] + ' desktop CLI',
        'notes': 'Six native desktop CLI archives and corresponding-source inputs.\n'
                 'Mobile AAR/XCFramework and final Polaris App/device acceptance are separate pending deliveries.\n'
                 'Frozen source: ' + expected + '\n', 'approvals': review, 'approvalsSha256': approvals_sha,
        'reviewedNativeIndexSha256': index_sha, 'nativeRun': index['workflowRun'], 'nativeAttempt': index['workflowAttempt'],
        'consumerKeys': {row['target']: row['consumerKey'] for row in config['desktop'] if row['consumerKey']},
        'publicUploadPerformed': False, 'tagCreated': False, 'mobileAcceptance': False, 'AppConsumerAcceptance': 'pending'}
    path = output / 'publication-manifest.json'
    path.write_bytes(encode(manifest))
    return {'manifest': file_info(path), 'plannedTagObject': object_sha, 'remoteWrites': False}


def validate_manifest(path, expected_hash, expected_head):
    require(sha(path.read_bytes()) == expected_hash, 'frozen publication manifest hash differs')
    m = json.loads(path.read_bytes())
    require(m['schema'] == 'polaris-production-publication-v1' and m['repository'] == REPOSITORY
            and m['repositoryId'] == REPOSITORY_ID and m['sourceCommit'] == expected_head
            and m['tag'] == 'v' + m['version'], 'publication identity differs')
    require(tag_sha(bytes.fromhex(m['tagObjectBytesHex'])) == m['tagObject'], 'prepared tag object differs')
    tag = bytes.fromhex(m['tagObjectBytesHex']).decode()
    require(tag.startswith('object ' + expected_head + '\ntype commit\ntag ' + m['tag'] + '\n'), 'prepared tag target/name differs')
    expected = {f"polaris-box-{m['version']}-{os_name}-{arch}" + ('.zip' if os_name == 'windows' else '.tar.gz')
                for os_name in ('linux', 'windows', 'darwin') for arch in ('amd64', 'arm64')}
    expected |= {'polaris-box-' + m['version'] + '-source.tar.gz', 'polaris-box-assets.json', 'SHA256SUMS'}
    require(len(m['assets']) == 9 and {a['name'] for a in m['assets']} == expected, 'exact nine assets required')
    for a in m['assets']:
        require(a['name'] and '/' not in a['name'] and '\\' not in a['name']
                and a['name'] not in ('.', '..'), 'simple asset name required')
        require(file_info(path.parent / a['name']) == a, 'frozen local asset differs: ' + a['name'])
    return m


def remote_tag(repo, m):
    text = command('git', '-C', repo, 'ls-remote', 'https://github.com/' + REPOSITORY + '.git',
                   'refs/tags/' + m['tag'], 'refs/tags/' + m['tag'] + '^{}')
    refs = {l.split()[1]: l.split()[0] for l in text.splitlines()}
    if not refs:
        return False
    require(refs == {'refs/tags/' + m['tag']: m['tagObject'], 'refs/tags/' + m['tag'] + '^{}': m['sourceCommit']},
            'existing tag differs; preserve it')
    return True


def validate_release(release, m, complete, release_id=None):
    if release_id is not None:
        require(release['id'] == release_id, 'inspected release ID differs')
    require(release['tag_name'] == m['tag'] and release['prerelease'] is True
            and release['name'] == m['title'] and release['body'] == m['notes'], 'release identity/notes differ')
    expected = {a['name']: a for a in m['assets']}
    actual = {a['name']: a for a in release['assets']}
    require(len(actual) == len(release['assets']) and set(actual) <= set(expected), 'unexpected/duplicate release assets; preserve')
    if complete:
        require(set(actual) == set(expected), 'incomplete release assets')
    require(len({a['id'] for a in actual.values()}) == len(actual), 'duplicate actual asset IDs')
    for name, a in actual.items():
        url = 'https://github.com/' + REPOSITORY + '/releases/download/' + m['tag'] + '/' + name
        require(type(a['id']) is int and a['id'] > 0 and a['browser_download_url'] == url, 'actual asset ID/URL differs')
        require(a['size'] == expected[name]['bytes'] and a.get('digest') == 'sha256:' + expected[name]['sha256'],
                'existing remote asset differs; never overwrite: ' + name)
    return set(expected) - set(actual)


def matching_releases(endpoint, tag):
    matches, page = [], 1
    while True:
        rows = api(endpoint + f'?per_page=100&page={page}')
        matches += [r for r in rows if r['tag_name'] == tag]
        if len(rows) < 100:
            return matches
        page += 1


def public_readback(m):
    results = []
    for a in m['assets']:
        url = 'https://github.com/' + REPOSITORY + '/releases/download/' + m['tag'] + '/' + a['name']
        request = urllib.request.Request(url, headers={'User-Agent': 'polaris-production-public-readback'})
        h, size = hashlib.sha256(), 0
        with urllib.request.urlopen(request, timeout=60) as response:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                require(size <= a['bytes'], 'public asset too large')
                h.update(chunk)
        require(size == a['bytes'] and h.hexdigest() == a['sha256'], 'anonymous public asset differs')
        results.append({**a, 'url': url, 'unauthenticatedReadback': True})
    return results


def execute(args):
    config, tree = frozen_source(args.repo, args.expected_head)
    m = validate_manifest(args.manifest, args.manifest_sha256, args.expected_head)
    require(m['version'] == config['version'] and m['tag'] == config['tag'] and m['sourceTree'] == tree, 'plan/source differs')
    with tempfile.TemporaryDirectory(prefix='polaris-production-upload-') as directory:
        snapshot = Path(directory)
        # Freeze all bytes before the first remote mutation, including tag creation.
        for a in m['assets']:
            shutil.copyfile(args.manifest.parent / a['name'], snapshot / a['name'])
            require(file_info(snapshot / a['name']) == a, 'upload snapshot differs')
        return execute_frozen(args, m, snapshot)


def execute_frozen(args, m, snapshot):
    require(api('repos/' + REPOSITORY)['id'] == REPOSITORY_ID, 'remote repository ID differs')
    endpoint = 'repos/' + REPOSITORY + '/releases'
    tagged = remote_tag(args.repo, m)
    if args.action == 'stage-draft':
        require(not tagged and not matching_releases(endpoint, m['tag']), 'existing tag/release; preserve and inspect')
        require(command('git', '-C', args.repo, 'remote', 'get-url', '--push', 'polaris')
                == 'https://github.com/' + REPOSITORY + '.git', 'fork push remote differs')
        actual = command('git', '-C', args.repo, 'mktag', data=bytes.fromhex(m['tagObjectBytesHex']))
        require(actual == m['tagObject'], 'actual tag object differs')
        command('git', '-C', args.repo, 'update-ref', 'refs/tags/' + m['tag'], actual, '0' * 40)
        command('git', '-C', args.repo, 'push', 'polaris', 'refs/tags/' + m['tag'] + ':refs/tags/' + m['tag'])
        require(remote_tag(args.repo, m), 'new remote tag not observed')
        release = api(endpoint, {'tag_name': m['tag'], 'name': m['title'], 'body': m['notes'],
                                'draft': True, 'prerelease': True, 'make_latest': 'false'})
    elif args.action == 'resume-tagged':
        require(tagged and not matching_releases(endpoint, m['tag']), 'exact tag and absent release required')
        release = api(endpoint, {'tag_name': m['tag'], 'name': m['title'], 'body': m['notes'],
                                'draft': True, 'prerelease': True, 'make_latest': 'false'})
    else:
        require(tagged and args.release_id is not None, 'exact remote tag and inspected release ID required')
        release = api(endpoint + '/' + str(args.release_id))
    if args.action in ('stage-draft', 'resume-tagged', 'resume-draft'):
        require(release['draft'] is True, 'only an exact inspected draft may receive missing assets')
        missing = validate_release(release, m, False, args.release_id)
        for name in sorted(missing):
            command('gh', 'release', 'upload', m['tag'], snapshot / name, '--repo', REPOSITORY)
        release = api(endpoint + '/' + str(release['id']))
        require(release['draft'] is True, 'draft changed during staging')
        validate_release(release, m, True, release['id'])
        return {'phase': 'draft-staged', 'releaseId': release['id'], 'tagObject': m['tagObject'], 'public': False}
    validate_release(release, m, True, args.release_id)
    if args.action == 'publish':
        require(release['draft'] is True, 'publish requires the exact staged draft')
        with tempfile.TemporaryDirectory(prefix='polaris-publish-patch-') as directory:
            payload = Path(directory) / 'publish.json'
            payload.write_bytes(encode({'draft': False, 'prerelease': True, 'make_latest': 'false'}))
            release = json.loads(command('gh', 'api', endpoint + '/' + str(args.release_id), '--method', 'PATCH', '--input', payload))
    require(release['draft'] is False, 'actual public release required')
    validate_release(release, m, True, args.release_id)
    observed = {'phase': 'public-awaiting-anonymous-readback', 'releaseId': release['id'],
                'tagObject': m['tagObject'], 'sourceCommit': m['sourceCommit'], 'sourceTree': m['sourceTree'],
                'version': m['version'], 'tag': m['tag'], 'public': True, 'anonymousReadback': False,
                'AppConsumerAcceptance': 'pending', 'mobileAcceptance': False, 'deviceAcceptance': False}
    if getattr(args, 'output', None):
        # Preserve the actual public state if a later download fails; no rollback,
        # deletion or false success receipt is inferred from an exception.
        args.output.write_bytes(encode(observed))
    downloaded = public_readback(m)
    after = api(endpoint + '/' + str(release['id']))
    require(after['draft'] is False and remote_tag(args.repo, m), 'public release/tag changed during readback')
    validate_release(after, m, True, release['id'])
    before_ids = {a['name']: a['id'] for a in release['assets']}
    require(before_ids == {a['name']: a['id'] for a in after['assets']}, 'actual asset IDs changed during readback')
    remote = {a['name']: a for a in after['assets']}
    actual_assets = [{**a, 'assetId': remote[a['name']]['id'], 'releaseId': release['id'],
                      'url': remote[a['name']]['browser_download_url']} for a in downloaded]
    index = json.loads((snapshot / 'polaris-box-assets.json').read_bytes())
    assets_by_name = {a['name']: a for a in actual_assets}
    consumer = {'schema': 'polaris-box-release-consumer-contract-v1', 'providerContract': 'polaris-box-release-v1',
                'repository': REPOSITORY, 'releaseId': release['id'], 'tag': m['tag'], 'tagObject': m['tagObject'],
                'sourceCommit': m['sourceCommit'], 'sourceTree': m['sourceTree'], 'version': m['version'],
                'assetIndex': assets_by_name['polaris-box-assets.json'], 'platforms': {}}
    for row in index['platforms']:
        key = m['consumerKeys'].get(row['target'])
        if key:
            consumer['platforms'][key] = {**row, 'releaseAsset': assets_by_name[row['archive']['name']]}
    consumer['actualAppAcceptance'] = 'pending owner actual release download/load/final carrier gate'
    return {**observed, 'phase': 'public-readback', 'anonymousReadback': True,
            'assets': actual_assets, 'consumerContract': consumer}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'stage-draft', 'resume-tagged', 'resume-draft', 'publish', 'readback'])
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--release-id', type=int)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--index-sha256')
    parser.add_argument('--approvals', type=Path)
    parser.add_argument('--approvals-sha256')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag-epoch')
    parser.add_argument('--tagger-name')
    parser.add_argument('--tagger-email')
    args = parser.parse_args()
    if args.action == 'prepare':
        require(all([args.inputs, args.index_sha256, args.approvals, args.approvals_sha256,
                     args.tag_epoch, args.tagger_name, args.tagger_email]), 'preparation arguments missing')
        result = prepare(args.repo, args.expected_head, args.inputs, args.index_sha256,
                         args.approvals, args.approvals_sha256, args.output, args.tag_epoch, args.tagger_name, args.tagger_email)
    else:
        require(args.manifest and args.manifest_sha256, 'frozen manifest and digest required')
        require(not args.output.exists() and not args.output.resolve().is_relative_to(args.repo.resolve()), 'fresh external receipt required')
        result = execute(args)
        args.output.write_bytes(encode(result))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
