# Glyphs MCP 2.0 runtime foundation

This directory is the canonical source for the in-progress Glyphs MCP 2.0
runtime. It is deliberately separate from the shipped 1.x plug-in resources
while the 2.0 contracts and host boundaries are being established.

The first vertical slice contains two read-only tools:

- `get_server_info`
- `list_open_fonts`

The package has five enforced layers:

- contracts and identities: host- and transport-independent values;
- application: read-only use cases and normalized failures;
- ports: immutable host snapshots and execution protocols;
- adapters: Glyphs 3.5/4 access isolated on the main thread;
- transport: catalog-driven FastMCP registration.

`contracts.py`, `identity.py`, `ports.py`, `catalog.py`, and `application.py`
must not import GlyphsApp, AppKit, Foundation, FastMCP, or Uvicorn.

## Worktree-contained development

From the repository root:

```bash
python3.12 -m venv .venv-v2
PIP_CACHE_DIR="$PWD/.cache/v2/pip" \
  .venv-v2/bin/python -m pip install -r requirements-dev.txt
PYTHONDONTWRITEBYTECODE=1 PYTHON_BIN=.venv-v2/bin/python \
  ./scripts/run_python_tests.sh
python3.12 scripts/build_v2_runtime_payload.py
```

The builder writes only to `build/v2-runtime/` by default. It does not install,
link, reload, or execute the plug-in in Glyphs.
