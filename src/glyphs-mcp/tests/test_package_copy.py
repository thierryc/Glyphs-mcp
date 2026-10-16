"""Package publication must never replace a source or an existing destination."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/protocol"))
SPEC = importlib.util.spec_from_file_location("package_copy", ROOT / "src/sidecar/glyphs_mcp_sidecar/package_copy.py")
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def native(_cli, _application, _source, package, _scratch):
    (package / "fontinfo.plist").write_text("verified")
    return {"glyphCount": 3, "masterCount": 2, "formatVersion": 4}


@pytest.fixture
def paths(tmp_path):
    source = tmp_path / "Font é.glyphs"
    source.write_bytes(b"saved source")
    return source, source.with_suffix(".glyphspackage")


def test_copy_publishes_verified_package_and_preserves_source(paths):
    source, destination = paths
    result = worker.create_copy(source, destination, "cli", "app", native=native)
    assert result["destination"] == str(destination.resolve())
    assert result["formatVersion"] == 4
    assert source.read_bytes() == b"saved source"
    assert (destination / "fontinfo.plist").read_text() == "verified"
    assert sorted(p.name for p in source.parent.iterdir()) == sorted([source.name, destination.name])


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_destination_is_never_overwritten(paths, kind):
    source, destination = paths
    if kind == "directory": destination.mkdir()
    elif kind == "symlink": destination.symlink_to(source.parent / "missing")
    else: destination.write_text("existing")
    with pytest.raises(FileExistsError):
        worker.create_copy(source, destination, "cli", "app", native=native)
    assert source.read_bytes() == b"saved source"
    assert os.path.lexists(destination)


def test_destination_created_while_verifying_is_preserved(paths):
    source, destination = paths
    def racing(*args):
        result = native(*args)
        destination.mkdir()
        (destination / "existing").write_text("keep")
        return result
    with pytest.raises(FileExistsError):
        worker.create_copy(source, destination, "cli", "app", native=racing)
    assert (destination / "existing").read_text() == "keep"
    assert not list(source.parent.glob(".glyphs-package-copy-*"))


def test_source_changed_during_verification_is_not_published(paths):
    source, destination = paths
    def changing(*args):
        result = native(*args)
        source.write_text("edited elsewhere")
        return result
    with pytest.raises(ValueError, match="source changed"):
        worker.create_copy(source, destination, "cli", "app", native=changing)
    assert source.read_text() == "edited elsewhere"
    assert not destination.exists()
    assert not list(source.parent.glob(".glyphs-package-copy-*"))


@pytest.mark.parametrize("failure", [ValueError("verification mismatch"), TimeoutError("timeout"), worker.CopyCancelled()])
def test_failure_cleans_partial_packages(paths, failure):
    source, destination = paths
    def failing(*args):
        native(*args)
        raise failure
    with pytest.raises(type(failure)):
        worker.create_copy(source, destination, "cli", "app", native=failing)
    assert list(source.parent.iterdir()) == [source]
    assert source.read_bytes() == b"saved source"


def test_cancellation_after_verification_prevents_publication(paths):
    source, destination = paths
    state = [False]
    def cancelling(*args):
        result = native(*args)
        state[0] = True
        return result
    with pytest.raises(worker.CopyCancelled):
        worker.create_copy(source, destination, "cli", "app", native=cancelling, cancelled=lambda: state[0])
    assert list(source.parent.iterdir()) == [source]


def test_source_symlink_and_different_output_directory_are_rejected(paths):
    source, destination = paths
    link = source.parent / "Link.glyphs"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="regular"):
        worker.create_copy(link, destination, "cli", "app", native=native)
    with pytest.raises(ValueError, match="beside"):
        worker.create_copy(source, source.parent / "sub/Font.glyphspackage", "cli", "app", native=native)


def test_canonical_comparison_only_ignores_glyph_timestamps(tmp_path):
    pytest.importorskip("Foundation")
    spec = importlib.util.spec_from_file_location("package_copy_native", ROOT / "src/sidecar/glyphs_mcp_sidecar/package_copy_native.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    first, second = tmp_path / "a.glyphs", tmp_path / "b.glyphs"
    first.write_text('{glyphs = ({glyphname=A; lastChange=old;}); userData={lastChange=keep;};}')
    second.write_text('{glyphs = ({glyphname=A;}); userData={lastChange=keep;};}')
    assert module.canonical(first) == module.canonical(second)
    second.write_text('{glyphs = ({glyphname=A;}); userData={lastChange=changed;};}')
    assert module.canonical(first) != module.canonical(second)


def test_sigterm_stops_native_process_and_cleans_stage(paths, tmp_path):
    source, destination = paths
    # A CLI double blocks like a long native conversion and records its PID.
    cli = tmp_path / "slow-cli"
    pidfile = tmp_path / "native.pid"
    cli.write_text(f'#!{sys.executable}\nimport os,time\nfrom pathlib import Path\nPath({str(pidfile)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n')
    cli.chmod(0o755)
    output = tmp_path / "result.json"
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"source":str(source), "destination":str(destination),
                                  "cli":str(cli), "application":"/missing.app", "result":str(output)}))
    process = subprocess.Popen([sys.executable, "-B", str(SPEC.origin), str(request)],
        env={**os.environ, "PYTHONPATH":str(ROOT / "src/protocol")})
    try:
        deadline = time.monotonic() + 10
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert pidfile.exists()
        process.terminate(); process.wait(timeout=8)
        assert json.loads(output.read_text())["cancelled"]
        assert not destination.exists()
        assert not list(tmp_path.glob(".glyphs-package-copy-*"))
        with pytest.raises(ProcessLookupError): os.kill(int(pidfile.read_text()), 0)
    finally:
        if process.poll() is None: process.kill(); process.wait()
