# Runtime path policy data flow

## Pre-fix audit

Before the shared policy, four surfaces independently reconstructed dependency
paths:

- `plugin.py` detected embedded Python, appended the external interpreter user
  site and the versioned Glyphs Scripts site, then separately promoted a
  Plugin Manager vendor tree.
- `runtime_probe.py` treated `--site-packages`, additional paths, allowed
  origins, user site, and the ambient runtime path as separate lists. Its
  static native-file scan could therefore reject a lower-priority copy that
  could not win at import time.
- `install_cli.py` inferred `--target` from the installer entry point and
  `--user` from the custom-Python entry point. Preflight and postflight rebuilt
  their own allowed-origin flags.
- `DepsInstaller` in the macOS installer made the same decision from the Swift
  `PythonSelection` case. Its distribution lookup inserted only the Glyphs
  Scripts directory, independently of startup ordering.

The v2 payload builder compared the generated `glyphs_mcp_v2` package, but did
not include the top-level runtime probe or a path-policy module in its manifest.

## Shared flow

The exact selected interpreter now runs `runtime_path_policy.py` through the
runtime probe. The probe returns one additive `pathPlan` object containing the
runtime kind, installation mode, primary root, fallbacks, and exact root order.

Installer preflight retains that object unchanged. Dependency metadata lookup,
pip destination and environment construction, and post-install verification
consume the retained plan. Postflight must return an equal plan or installation
is rejected. Plug-in startup calls the same builder and applicator; an ABI-
matched Plugin Manager vendor directory remains a separate higher-priority
override.

`runtime_probe.py` discovers candidates in `orderedRoots`, evaluates native
compatibility only for the candidate that can win, and reports lower-priority
duplicates and incompatibilities as nonblocking diagnostics. Logical and
resolved origins are classified against the same approved roots so a symlink
may cross between approved roots but may not escape them.
