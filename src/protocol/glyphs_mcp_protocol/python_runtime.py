"""Resolve Glyphs 4's default Plugin Manager Python for external launchers.

glyphs-cli 0.6.1 reads GSPythonFrameworkPath but does not discover the default
module when that preference is absent. Keep explicit selections authoritative.
This module is standalone so installer preflight can load it without importing
the protocol package or any private-runtime dependencies.
"""

from pathlib import Path
import plistlib
import subprocess


def is_glyphs4_application(metadata):
    identifier = metadata.get("CFBundleIdentifier")
    return identifier in {"com.GeorgSeifert.Glyphs4", "com.GeorgSeifert.Glyphs4Beta"} or (
        identifier == "com.GeorgSeifert.GlyphsBeta" and str(metadata.get("CFBundleShortVersionString", "")).startswith("4")
    )


def python_arguments(application, *, home=None, diagnostic=None):
    """Return an explicit CLI framework selection, or retain CLI diagnostics.

    Resolve the exact application's preferences, never another Glyphs version.
    Only an absent setting permits discovery of the official Glyphs 4 module.
    Do not substitute system Python or the older Glyphs 3 Python module.
    """
    def emit(event, **values):
        if diagnostic is not None:
            diagnostic({"event": event, **values})

    def observation(path):
        try:
            return {"path": str(path), "exists": path.exists(), "isFile": path.is_file(),
                    "resolvedPath": str(path.resolve()) if path.exists() else None}
        except (OSError, RuntimeError) as error:
            return {"path": str(path), "inspectionError": str(error)}

    info = Path(application) / "Contents/Info.plist"
    if not info.is_file():
        emit("python.app", path=str(application), infoPlist="missing")
        return []
    metadata = plistlib.loads(info.read_bytes())
    identifier = metadata.get("CFBundleIdentifier")
    emit("python.app", path=str(application), resolvedPath=str(Path(application).resolve()),
         bundleIdentifier=identifier, version=metadata.get("CFBundleShortVersionString"),
         build=metadata.get("CFBundleVersion"))
    if not is_glyphs4_application(metadata):
        emit("python.selection", source="cli-preference", reason="unsupported-default-module-domain")
        return []
    result = subprocess.run(
        ["/usr/bin/defaults", "read", identifier, "GSPythonFrameworkPath"],
        capture_output=True, text=True, timeout=5,
    )
    candidates = []
    if diagnostic is not None or result.returncode != 0:
        roots = (Path(home) if home is not None else Path.home(), Path("/"))
        candidates = [root / "Library/Application Support/Glyphs 4/Repositories/Python/Python.framework/Versions/Current/Python"
                      for root in roots]
        if diagnostic is not None:
            emit("python.default-candidates", candidates=[observation(path) for path in candidates])
    if result.returncode == 0:
        selected = result.stdout.strip()
        if diagnostic is not None:
            try:
                selected_path = Path(selected).expanduser() if selected else None
                emit("python.preference", domain=identifier, key="GSPythonFrameworkPath", state="present" if selected else "empty",
                     selectedPath=selected, settingPath=observation(selected_path) if selected_path else None,
                     selectedFramework=observation(selected_path if selected_path.is_file() else selected_path / "Python")
                     if selected_path else None)
            except (OSError, RuntimeError) as error:
                emit("python.preference", domain=identifier, state="present", selectedPath=selected, inspectionError=str(error))
        emit("python.selection", source="cli-preference", reason="explicit-setting-retained")
        # Let the CLI honor explicit paths, including broken/disabled settings;
        # detecting a module is not permission to change the user's selection.
        return []
    if "does not exist" not in result.stderr:
        emit("python.preference", domain=identifier, state="read-error", exitCode=result.returncode, stderr=result.stderr)
        raise ValueError("Could not read the selected Glyphs Python setting: " + result.stderr.strip())
    emit("python.preference", domain=identifier, key="GSPythonFrameworkPath", state="absent", exitCode=result.returncode)
    for framework in candidates:
        if framework.is_file():
            selected = str(framework.resolve())
            emit("python.selection", source="default-module", framework=selected)
            return ["--python", selected]
    emit("python.selection", source="cli-preference", reason="no-default-module-found")
    return []
