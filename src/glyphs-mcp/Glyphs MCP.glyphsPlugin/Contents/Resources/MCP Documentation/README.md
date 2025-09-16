# MCP Documentation

This directory contains tools for building reStructuredText documentation for the MCP server.
The generator reads documentation blocks from ``../GlyphsApp/__init__.py``
and writes them into a ``docs/`` folder (ignored by Git). It also creates
an ``index.json`` file that maps each section name to its first line so the
MCP server or an LLM can quickly locate relevant topics.

## Requirements

- Python 3.9+

## Setup

Create a virtual environment (recommended) and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Usage

Extract documentation and build the source directory:

```bash
python mcp_doc_generator.py
```

The script creates ``index.json`` alongside per-section ``section_*.rst``
files in ``docs/``. Because ``docs/`` is ignored, only ``index.json`` is
tracked, providing a lightweight map for documentation retrieval.
