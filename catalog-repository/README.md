# Glyphs MCP skills

A reviewed catalog of skills for Glyphs and font workflows. Browse and install
skills from **Skills** in the Glyphs MCP desktop app (2.0.1 or later).

- **Included** skills ship with Glyphs MCP and are managed with agent setup.
- **Curated** skills are selected by maintainers.
- **Community** skills are reviewed contributions.
- Personal GitHub imports remain unreviewed and are never published automatically.

Skills use the open [Agent Skills format](https://agentskills.io/specification):
a `SKILL.md` folder with optional scripts, references and assets. Install skills
in your AI client; required MCP connections provide tools separately.

See [CONTRIBUTING.md](CONTRIBUTING.md) to propose a skill or an update. Start with
[the template](template/example-skill/SKILL.md), copy it to `skills/<name>/`, and
include example prompts and expected results. You may instead register a pinned
skill maintained in your own public GitHub repository.

Local copies work in Codex, Cursor and Claude Code. ChatGPT and Claude imports
use a ZIP upload where supported by the user's account. Uploading a skill does
not make a local Glyphs bridge accessible to hosted execution.

```sh
python -m pip install -r requirements-validation.txt
python scripts/validate_catalog.py
python scripts/validate_catalog.py --fetch-sources
python -m unittest discover -s tests
```

Validation reads metadata and files. It never runs contributed scripts. Catalog
updates require a pull request and maintainer review; dependencies and client
compatibility require evidence rather than a claim of universal support.

Registry metadata and starter material are Apache-2.0 licensed. Each skill retains its
own license and attribution, including original licenses on supporting assets.
