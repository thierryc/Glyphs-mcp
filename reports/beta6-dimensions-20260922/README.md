# Beta 6 Dimensions evidence

Run on September 22, 2026. See [BETA6-VALIDATION.md](../../BETA6-VALIDATION.md)
for scope, results and remaining release gates.

- `native.json`: 204 checks of the real Glyphs 4.1 (4107) palette,
  GSDocument, native Undo/Redo, clear, discard, and both font serialization
  formats, using disposable fonts in an isolated CLI process.
- `native.log.gz`: complete native qualification output. The Glyphs CLI emits
  Bugsnag-not-started warnings; the qualification exits successfully.
- `local-release-tests.log.gz`: successful full local release gate, including
  2,115 Python passes (one skip), 203 macOS tests, deterministic builds, private
  runtime qualification, documentation build and unsigned desktop validation.
- `focused.log`: final 48 Dimensions tests, including eight recovery and
  precision cases added after the complete Python matrix. Runtime sources did
  not change after that matrix.
- `candidate-manifest.json`: deterministic Beta 6/build 48 candidate identity.
- `candidate-source-match.json`: comparison of all packaged runtime Python
  files against the final sources.
- `source-fingerprints.json`: SHA-256 hashes of runtime Python sources and
  the focused/native qualification scripts.

Repeat the native check with:

```sh
PYTHONDONTWRITEBYTECODE=1 build/private-runtime/arm64/bin/glyphs run \
  --app '/Applications/Glyphs 4.app' --plugins '' \
  scripts/qualify_dimensions_native.py
```

It writes disposable fonts and evidence under `build/dimensions-beta6`.
This proof is independent of the installed MCP, which remains Beta 5. It does
not claim deployment, signing, notarization or acceptance through a newly
installed connection.
