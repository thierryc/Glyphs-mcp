# Offline Glyphs 4 documentation

The installed skill includes `assets/knowledge/index.json`, its manifest and
all available pinned SDK sources/references and vendored handbook pages.
Guide illustrations and sample binary assets are retained unchanged with their
checksums; only UTF-8 text is indexed. Generated build/cache files are excluded.
The local helper does not execute sample assets. No repository, v1,
running Glyphs process or internet connection is needed.

Run from this skill directory, or resolve the absolute helper path:

```text
python3 scripts/docs.py search "ReporterPlugin foreground" --limit 5
python3 scripts/docs.py search "GSLayer.selection"
python3 scripts/docs.py get api-section-340 --offset 0 --max-chars 4000
```

Use the actual search result ID; the number above illustrates syntax. Search
defaults to five results and caps at 20, with `totalCount`, `returnedCount`
and `complete`. A ranked subset is not exhaustive evidence. Get defaults to
4,000 characters and caps at 12,000, with `totalChars`, `returnedChars`,
`offset`, `truncated` and `nextOffset`. `complete` means that response contains
the whole document; a final nonzero-offset slice is not the whole page.
Follow offsets only when needed. Reuse a returned documentation ID to fetch its
next needed section directly; do not search again to recover an ID still in context.

Choose the source by the question: native API behavior belongs in this corpus;
private MCP boundaries and document-ID lifetime belong in the entry skill;
installation failures and loaded revisions belong in the native iteration and
recovery references. Official SDK text cannot establish private MCP behavior.
For a broad question, identify the likely native owner or plugin type and search
those terms. Inspect the first five summaries before fetching; reformulate once
with the returned symbol or guide title if needed. An irrelevant first hit is
not an answer. Reuse a useful citation and excerpt from the same installed corpus
instead of refetching them for each follow-up. After context loss, read only the
missing reference/section. After a skill/corpus update or inconsistent evidence,
refresh the affected source; reuse does not turn an unavailable source into proof.
Ranking favors API sections and guides over incidental source-file directory
names. Exact symbols, indexed paths and titles remain directly searchable.

| Need | Search |
|---|---|
| Plugin choice, installation/relaunch | `Plug-ins`, `Python Templates README` |
| Reporter lifecycle and labels | `Reporter foreground drawTextAtPoint` |
| Selected objects and indices | `GSLayer.selection`, `GSNode`, `GSLayer.paths`, `GSLayer.shapes` |
| Native callback | Exact class/method name |
| Font-design operation | Handbook topic: `spacing`, `masters`, `guides` |
| Serialization | `GlyphsFileFormatv4`, or explicitly version 3 |

Prefer small qualified API sections to full wrapper source. Original sources,
examples and template guides cover details omitted by section extraction.
Results carry source paths/URLs, revision and SHA-256. The vendored handbook's
exact upstream revision is unavailable; per-file hashes identify its snapshot.
Historical file-format versions do not change this skill's Glyphs 4 app target.

`nativeVerification` explicitly distinguishes source documentation from a
native test. Report undocumented selectors and uncertain index relationships
as uncertain; prove them in bounded disposable native tests when authorised.
Project instructions and qualification notes are separate from official text.
For native export keywords, feature flags and compiler results, read
[qualified Glyphs 4 API notes](glyphs4-api-notes.md); for coordinate writes, use
[native precision](native-precision.md). These focused notes preserve the pinned
official corpus and identify the host actually tested.

`update_required` means missing, corrupt or unsupported installed evidence.
Update the development skill through the existing installer; do not silently
substitute v1, retired typed-v2 tools or online material. Unknown documentation
IDs need a local search, not font discovery. The standard-library helper only
reads indexed local files; it has no network, GlyphsApp or execution route.
