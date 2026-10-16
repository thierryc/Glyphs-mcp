"""Desktop-only package copy transaction; no live font or sidecar connection needed."""

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import uuid

from glyphs_mcp_protocol.python_runtime import python_arguments


class CopyCancelled(Exception):
    pass


def source_hash(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Choose a regular .glyphs file, not a symbolic link")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_paths(source, destination):
    if not source.is_absolute() or source.suffix.lower() != ".glyphs":
        raise ValueError("Choose an absolute .glyphs source file")
    source_hash(source)
    source = source.parent.resolve() / source.name
    if (not destination.is_absolute() or destination.suffix != ".glyphspackage"
            or destination.parent.resolve() != source.parent):
        raise ValueError("The package copy must be beside its source")
    destination = source.parent / destination.name
    if os.path.lexists(destination):
        raise FileExistsError("A file already exists at the package destination. Choose another name.")
    return source, destination


def publish(package, destination):
    # RENAME_EXCL guarantees that a destination created during verification is
    # never replaced, including an empty directory or a dangling symlink.
    library = ctypes.CDLL(None, use_errno=True)
    rename = library.renamex_np
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(os.fsencode(package), os.fsencode(destination), 0x00000004) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError("A file already exists at the package destination. Choose another name.")
        raise OSError(code, os.strerror(code))


def run_native(cli, application, source, package, scratch, timeout=300):
    request = scratch / "native-request.json"
    result = scratch / "native-result.json"
    request.write_text(json.dumps({"source": str(source), "package": str(package),
                                   "scratch": str(scratch), "result": str(result)}), encoding="utf-8")
    command = [str(cli), "run", "--quiet", "--app", str(application), "--plugins", "",
               *python_arguments(application), str(Path(__file__).with_name("package_copy_native.py")),
               "--", str(request)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        if process.returncode:
            if result.exists():
                failure = json.loads(result.read_text(encoding="utf-8"))
                if isinstance(failure.get("error"), str):
                    raise ValueError(failure["error"])
            raise ValueError((stderr or stdout or "Glyphs conversion failed").strip()[-4000:])
        value = json.loads(result.read_text(encoding="utf-8"))
        if (set(value) != {"glyphCount", "masterCount", "formatVersion"}
                or any(type(number) is not int or number < 0 for number in value.values())):
            raise ValueError("Glyphs returned an invalid verification result")
        return value
    except subprocess.TimeoutExpired as error:
        raise TimeoutError("Glyphs package conversion timed out") from error
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()


def create_copy(source, destination, cli, application, *, native=run_native,
                cancelled=lambda: False, publication=publish):
    source, destination = validate_paths(Path(source), Path(destination))
    before = source_hash(source)
    scratch = Path(tempfile.mkdtemp(prefix=".glyphs-package-copy-", dir=source.parent))
    package = source.parent / (".glyphs-package-copy-" + uuid.uuid4().hex + ".glyphspackage")
    canonical = [source.parent / (scratch.name + ending) for ending in (".before.glyphs", ".after.glyphs")]
    owned_canonical = []
    owned_package = False
    try:
        package.mkdir(mode=0o700)
        owned_package = True
        for path in canonical:
            path.touch(mode=0o600, exist_ok=False)
            owned_canonical.append(path)
        if cancelled():
            raise CopyCancelled()
        summary = native(cli, application, source, package, scratch)
        if source_hash(source) != before:
            raise ValueError("The source changed during conversion. Create the package copy again.")
        if cancelled():
            raise CopyCancelled()
        publication(package, destination)
        return {"destination": str(destination), "sourceSHA256": before, **summary}
    finally:
        if owned_package:
            shutil.rmtree(package, ignore_errors=True)
        shutil.rmtree(scratch, ignore_errors=True)
        for path in owned_canonical:
            path.unlink(missing_ok=True)


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = Path(request["result"])
    was_cancelled = False
    completed = False

    def cancel(_signum, _frame):
        nonlocal was_cancelled
        was_cancelled = True
        if not completed:
            raise CopyCancelled()

    signal.signal(signal.SIGTERM, cancel)
    try:
        # Block delivery across publication and result writing so cancellation
        # can be reconciled after a successful atomic move.
        def guarded_publish(package, destination):
            nonlocal completed
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
            try:
                publish(package, destination)
                completed = True
            finally:
                if not completed:
                    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})

        # Pass publication as a dependency instead of changing global behavior.
        result = create_copy(request["source"], request["destination"], request["cli"],
                             request["application"], cancelled=lambda: was_cancelled,
                             publication=guarded_publish)
        value = {"ok": True, "data": result}
    except CopyCancelled:
        value = {"ok": False, "cancelled": True, "error": "Package copy cancelled"}
    except Exception as error:
        value = {"ok": False, "error": str(error)}
    output.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
