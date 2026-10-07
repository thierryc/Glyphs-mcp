# Beta 9 release — September 28, 2026

Published [Beta 9 prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.9), desktop build 51.
Signed tag source: `68bf1fdf673285988a886fdf5a3c6471e2f533c0` on `lit/v2-beta`.

- Complete local gate and guarded publisher gate passed: 2,464 Python tests,
  two skips, five warnings; 220 desktop tests, zero failures.
- Deterministic payloads, both private runtimes, 11 synchronized skills,
  12 tools, website build and source metadata checks passed.
- Developer ID signing, all three Apple notarization submissions, stapling,
  Gatekeeper, nested signatures and signature-preserving install copies passed.
- Both signed private runtimes passed startup, packaged installer CLI, HTTP
  catalog, stdio proxy, MCP App resource and structured/text response checks.
- Four public assets downloaded without authentication and matched local bytes;
  the signed Sparkle feed and ZIP verified. Stable Latest remains v1.11.1.
- The exact signed Beta 9 feed is published on the beta branch.

Beztrace is an informational card with setup guidance. Its independent plugin
is not installed, bundled, signed or qualified by this release. No Glyphs
restart, runtime replacement or font mutation was performed for Beta 9.

The user approved publication after reviewing [the validation note](https://github.com/thierryc/Glyphs-mcp/blob/v2.0.0/BETA9-VALIDATION.md).
The exact signed-update/component-migration trial, physical Intel/minimum macOS,
narrow-window/dark-mode review, and carried-forward Beta 8 group-pair native UI
Undo and exact-pair card visual acceptance remain unperformed or unresolved.

See `distribution-state.json`, `signed-runtimes.json`,
`public-download-verification.json`, and `github-published.json` for identities.
