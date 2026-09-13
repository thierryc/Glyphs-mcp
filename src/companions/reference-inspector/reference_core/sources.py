"""Read local sources and pinned Git revisions outside Glyphs' UI process."""

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 20000


def _git(*args, timeout=60):
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1")
    executable = shutil.which("git")
    if not executable or executable == "/usr/bin/git" and subprocess.run(
            ["/usr/bin/xcode-select", "-p"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise ValueError("Git references require Git. Install Git or use Last Saved / Font File.")
    result = subprocess.run([executable, *map(str, args)], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, env=environment)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip()[-1000:] or "Git reference unavailable")
    return result.stdout


def github_url(value):
    parsed = urlparse(str(value).strip())
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment
            or len(parts) != 2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) or p in {".", ".."} for p in parts)):
        raise ValueError("Use a public https://github.com/owner/repository URL")
    return "https://github.com/" + "/".join(parts) + ".git"


def _font_path(value):
    path = PurePosixPath(str(value))
    if path.is_absolute() or ".." in path.parts or str(path).startswith("-") or path.suffix.lower() not in {".glyphs", ".glyphspackage"}:
        raise ValueError("Choose a repository-relative .glyphs or .glyphspackage path")
    return path.as_posix()


def source_hash(path):
    path = Path(path)
    if path.is_symlink() or path.suffix.lower() not in {".glyphs", ".glyphspackage"}:
        raise ValueError("Choose a saved .glyphs or .glyphspackage reference")
    if path.suffix.lower() == ".glyphs":
        files = [path]
    elif path.is_dir():
        entries = list(path.rglob("*"))
        if any(p.is_symlink() for p in entries):
            raise ValueError("Reference packages must not contain symbolic links")
        files = sorted(p for p in entries if p.is_file())
    else:
        files = []
    if not files or len(files) > MAX_FILES:
        raise ValueError("The reference is missing or exceeds the file limit")
    digest, total = hashlib.sha256(), 0
    for file in files:
        total += file.stat().st_size
        if total > MAX_BYTES:
            raise ValueError("The reference exceeds the size limit")
        relative = (file.relative_to(path).as_posix() if path.is_dir() else "source").encode()
        digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def resolve_reference(spec, live_path, cache, *, refresh=False):
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    kind = spec.get("kind", "last_saved")
    commit = None
    if kind in {"last_saved", "file"}:
        source = Path(live_path if kind == "last_saved" else spec.get("source", "")).expanduser()
        identity = source_hash(source)
        target = cache / (identity + source.suffix.lower())
        if not target.exists():
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            if source_hash(source) != identity or source_hash(target) != identity:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                raise ValueError("The reference changed while it was copied; refresh it")
        label = "Last Saved" if kind == "last_saved" else source.name
    elif kind in {"local_git", "github"}:
        revision = str(spec.get("revision") or "HEAD").strip()
        if revision.startswith("-") or not revision or "\x00" in revision:
            raise ValueError("Choose a Git branch, tag, or commit")
        if kind == "github":
            url = github_url(spec.get("source", ""))
            repo = cache / (hashlib.sha256(url.encode()).hexdigest() + ".git")
            if not repo.exists():
                _git("clone", "--bare", "--", url, repo)
            elif refresh:
                _git("-C", repo, "fetch", "--prune", "origin", "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")
        else:
            repo = Path(spec.get("source") or Path(live_path).parent).expanduser().resolve()
        commit = _git("-C", repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise ValueError("Git did not resolve one commit")
        requested = spec.get("fontPath")
        if not requested and kind == "local_git":
            top = Path(_git("-C", repo, "rev-parse", "--show-toplevel").decode().strip())
            requested = Path(live_path).resolve().relative_to(top).as_posix()
        font_path = _font_path(requested or "")
        identity = hashlib.sha256((str(repo) + commit + font_path).encode()).hexdigest()
        directory = cache / identity
        target = directory / font_path
        if not target.exists():
            archive = _git("-C", repo, "archive", "--format=tar", commit, "--", font_path)
            if len(archive) > MAX_BYTES:
                raise ValueError("The reference archive exceeds the size limit")
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                members = tar.getmembers()
                if len(members) > MAX_FILES or sum(m.size for m in members) > MAX_BYTES:
                    raise ValueError("The reference archive exceeds the size limit")
                for member in members:
                    name = PurePosixPath(member.name)
                    if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                        raise ValueError("The reference archive contains an unsafe entry")
                    destination = directory / name
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with tar.extractfile(member) as stream, destination.open("wb") as output:
                            shutil.copyfileobj(stream, output)
        source_hash(target)
        label = f"{revision} @ {commit[:8]}"
    else:
        raise ValueError("Unsupported comparison reference")
    return {"path": str(target), "identity": identity, "label": label, "commit": commit}
