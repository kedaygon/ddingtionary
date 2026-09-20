import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

OWNER = "Arikatsu"
REPO = "WutheringWaves_Data"
REPO_URL = "https://github.com/%s/%s.git" % (OWNER, REPO)
RAW_BASE = "https://raw.githubusercontent.com/%s/%s" % (OWNER, REPO)
API_BRANCHES = "https://api.github.com/repos/%s/%s/branches?per_page=100" % (OWNER, REPO)

UA = "wuwaskill-importer"
TIMEOUT = 120

NEEDED_PATHS = [
    "BinData/role/roleinfo.json",
    "BinData/skill/skill.json",
    "BinData/skill/skilldescription.json",
    "BinData/skill/skilllevel.json",
    "BinData/skill/skilltype.json",
    "BinData/skillTree/skilltree.json",
    "BinData/skillTree/skillcondition.json",
    "BinData/resonate_chain/resonantchain.json",
    "Textmaps/ko/multi_text/MultiText.json",
]

EXTRA_PATHS = [
    "BinData/property/baseproperty.json",
    "BinData/property/rolepropertygrowth.json",
    "BinData/property/weaponpropertygrowth.json",
    "BinData/property/propertyindex.json",
    "BinData/weapon/weaponconf.json",
    "BinData/phantom/phantommainproperty.json",
    "BinData/phantom/phantommainpropitem.json",
    "BinData/phantom/phantomgrowth.json",
    "BinData/phantom/phantomfetter.json",
    "BinData/phantom/phantomfettergroup.json",
    "BinData/monster_Info/monsterinfo.json",
]

_VERSION_RE = re.compile(r"^\d+\.\d+$")


class ImportError_(Exception):
    pass


def _force_writable(func, path, exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rmtree(path):
    if not os.path.isdir(path):
        return True
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_writable)
    else:
        shutil.rmtree(path, onerror=_force_writable)
    return not os.path.isdir(path)


def _sweep_stale(cache_root, version):
    prefix = version + ".tmp"
    try:
        names = os.listdir(cache_root)
    except OSError:
        return
    for n in names:
        if n.startswith(prefix):
            _rmtree(os.path.join(cache_root, n))


def _version_key(v):
    return tuple(int(x) for x in v.split("."))


def _open(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _versions_from_git():
    try:
        p = subprocess.run(
            ["git", "ls-remote", "--heads", REPO_URL],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if p.returncode != 0:
        return []
    out = []
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2:
            name = parts[1].rsplit("/", 1)[-1]
            if _VERSION_RE.match(name):
                out.append(name)
    return out


def _versions_from_api():
    try:
        with _open(API_BRANCHES) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as e:
        raise ImportError_("branch lookup failed: %s" % e)
    return [b["name"] for b in data if _VERSION_RE.match(b.get("name", ""))]


def list_versions():
    v = _versions_from_git() or _versions_from_api()
    if not v:
        raise ImportError_("no version branches found")
    return sorted(set(v), key=_version_key)


def latest_version():
    return list_versions()[-1]


def cached_versions(cache_root):
    if not os.path.isdir(cache_root):
        return []
    out = [n for n in os.listdir(cache_root)
           if _VERSION_RE.match(n) and is_complete(os.path.join(cache_root, n))]
    out.sort(key=_version_key)
    return out


def is_complete(version_dir):
    return all(os.path.isfile(source_path(version_dir, p)) for p in NEEDED_PATHS)


def _download(url, dest, progress=None, label=""):
    for attempt in range(3):
        try:
            return _download_once(url, dest, progress, label)
        except ImportError_:
            if attempt == 2:
                raise
            time.sleep(1.5)


def _download_once(url, dest, progress=None, label=""):
    tmp = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        with _open(url) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            step = max(total // 10, 1 << 21) if total else 1 << 22
            nxt = step
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress and done >= nxt:
                        if total:
                            progress("download", "%s %.1f/%.1f MB" % (
                                label, done / 1048576.0, total / 1048576.0))
                        else:
                            progress("download", "%s %.1f MB" % (label, done / 1048576.0))
                        nxt += step
        if total and done != total:
            raise ImportError_("download cut off for %s (%d/%d bytes)" % (url, done, total))
    except urllib.error.HTTPError as e:
        raise ImportError_("HTTP %s for %s" % (e.code, url))
    except (urllib.error.URLError, OSError) as e:
        raise ImportError_("download failed for %s: %s" % (url, e))
    if os.path.exists(dest):
        os.remove(dest)
    os.replace(tmp, dest)
    return dest


def fetch(version, cache_root, progress=None, force=False):
    target = os.path.join(cache_root, version)
    if is_complete(target) and not force:
        if progress:
            progress("cached", version)
        if missing_extra(target):
            try:
                fetch_extra(target, progress)
            except Exception:
                pass
        return target

    os.makedirs(cache_root, exist_ok=True)
    _sweep_stale(cache_root, version)
    work = "%s.tmp-%d-%d" % (target, os.getpid(), int(time.time()))
    os.makedirs(work, exist_ok=True)

    try:
        for i, rel in enumerate(NEEDED_PATHS, 1):
            label = "%d/%d %s" % (i, len(NEEDED_PATHS), rel.rsplit("/", 1)[-1])
            if progress:
                progress("fetch", label)
            _download(
                "%s/%s/%s" % (RAW_BASE, version, rel),
                source_path(work, rel),
                progress=progress,
                label=label,
            )
    except Exception:
        _rmtree(work)
        raise

    try:
        fetch_extra_into(work, version, progress)
    except Exception:
        pass

    if not is_complete(work):
        _rmtree(work)
        raise ImportError_("incomplete download for version %s" % version)

    if os.path.isdir(target):
        for rel in NEEDED_PATHS + EXTRA_PATHS:
            src = source_path(work, rel)
            if not os.path.isfile(src):
                continue
            dst = source_path(target, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                os.replace(src, dst)
            except OSError as e:
                _rmtree(work)
                raise ImportError_("데이터 파일을 바꾸지 못했습니다 (%s): %s" % (e, dst))
        _rmtree(work)
    else:
        os.replace(work, target)

    if progress:
        progress("done", version)
    return target


def fetch_extra_into(work, version, progress=None):
    for i, rel in enumerate(EXTRA_PATHS, 1):
        label = "추가 %d/%d %s" % (i, len(EXTRA_PATHS), rel.rsplit("/", 1)[-1])
        if progress:
            progress("fetch", label)
        _download("%s/%s/%s" % (RAW_BASE, version, rel),
                  source_path(work, rel), progress=progress, label=label)


def missing_extra(version_dir):
    return [p for p in EXTRA_PATHS if not os.path.isfile(source_path(version_dir, p))]


def fetch_extra(version_dir, progress=None):
    version = os.path.basename(os.path.normpath(version_dir))
    todo = missing_extra(version_dir)
    for i, rel in enumerate(todo, 1):
        label = "%d/%d %s" % (i, len(todo), rel.rsplit("/", 1)[-1])
        if progress:
            progress("fetch", label)
        _download("%s/%s/%s" % (RAW_BASE, version, rel),
                  source_path(version_dir, rel), progress=progress, label=label)
    return not missing_extra(version_dir)


def source_path(version_dir, rel):
    return os.path.join(version_dir, *rel.split("/"))
