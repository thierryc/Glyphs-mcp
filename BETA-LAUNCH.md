# Glyphs MCP 2.0.0 Beta 4 — release and launch plan

## Decision

Prepare **2.0.0 Beta 4**, tag `v2.0.0-beta.4`, build **46**, on `lit/v2-beta`.
Keep all v2 application and registry work off `main` through the beta cycle.
Use an open download with optional enrollment. Focus communication on the
Glyphs forum, GitHub and Thierry's social accounts. Thierry handles the first
email to Nadine separately; no email or announcement has been sent.

The public promise is a beta to try and help improve. Avoid “2.0 is released,”
“production ready,” or guaranteed dates for a final release.

## Distribution

- Use a GitHub **prerelease**, titled **Glyphs MCP 2.0.0 Beta 4**. Keep
  `make_latest=false`. A public beta branch, tag and prerelease are public by
  design. [GitHub release controls](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
- Publish the versioned DMG, versioned Sparkle ZIP, `appcast.xml` and
  `SHA256SUMS`. Never publish a beta as `Glyphs-MCP-latest.dmg`.
- Use `BETA.md` on the beta branch as the initial landing page. It can carry
  installation guidance and exact download links without deploying over the
  existing GitHub Pages site. Keep the stable release and site unchanged.
- Keep the registry at `lit/v2-beta/templates/registry.json`. Validate changes,
  pin archives to commits and SHA-256, then publish registry-only changes on
  that branch. Refresh loads the new list; installed projects are unchanged.
- Use `lit/v2-beta/appcast.xml` only for beta updates. Keep build numbers
  increasing: 45, 46, 47… even though the marketing version was renumbered.
  Update signatures and build ordering follow the
  [Sparkle publishing model](https://sparkle-project.org/documentation/publishing/).
- Preserve the service identity. Qualify upgrades and rollback, including
  restored settings and component receipts; do not market side-by-side server
  isolation. The Beta 4 payload is Glyphs 4-only; Glyphs 3 remains on its
  separate pinned v1.11.0 release.

## Release sequence

1. Review the full accumulated worktree, including the UI fixes, and run the
   complete local release gates. Confirm lean payload reproducibility, hashes,
   Python and macOS tests, documentation and private runtime checks.
2. Test disposable fonts and the installer on Apple silicon and Intel, minimum
   and current macOS, with the actual supported Glyphs 4 builds. Cover fresh
   install, upgrade, component/connector removal, Cursor ownership conflicts,
   absent agents, reload guidance, preserved settings, rollback, native
   Save/Undo/Redo/discard, templates online/offline, logs, window resizing and dark mode.
   Record actual versions and outcomes; do not infer support from compilation.
3. Commit the reviewed candidate on `lit/v2-beta`. Push that branch and create
   the matching signed beta tag only when the source is ready for publication.
   Do not merge it into `main`.
4. Build locally, sign with Developer ID, notarize and staple, create the DMG,
   and generate signed Sparkle assets. Check Gatekeeper and perform a signed
   update trial. Keep the candidate private until these pass.
5. Create an empty draft GitHub prerelease targeting the beta tag. The existing
   publisher enforces the branch, clean source, exact local/remote tag, tests,
   signatures and uploaded asset hashes. Review the concrete assets and notes
   before publishing. Example final command, only at that stage:

   ```sh
   ./scripts/publish_release_assets.sh --tag v2.0.0-beta.4 --publish --confirm-publish v2.0.0-beta.4
   ```

6. Verify the exact public download and checksum, then commit the exact signed
   appcast bytes to the beta branch. Verify both raw registry/feed URLs from a
   clean machine. Replace BETA.md's preparation notice with the verified
   release link and tested compatibility/rollback instructions.
7. Confirm GitHub's stable Latest release still identifies the previous stable
   release. Publish the communication below only after the beta download works.

Beta 5 uses `--beta 5` and a higher installer build. Final 2.0.0 gets a new
higher build and tag, final qualification, and a separately reviewed merge to
`main`. Do not relabel Beta 4 as final or repoint its tag.

## Enrollment and feedback

Open downloads have no registration gate. Invite roughly 10–20 volunteers for
a focused first cohort across processors, macOS versions, AI clients and font
workflows. Ask for one first-session report and one workflow report; opt-in
participants receive follow-ups in their GitHub issue, not unsolicited email.

Use BETA.md's prefilled issue links immediately. They need no default-branch
change; GitHub issue templates themselves must live on the default branch.
[GitHub template behavior](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates).
GitHub Discussions is currently disabled; enabling it and pinning a beta
announcement is an optional publication-time step, not a prerequisite.

Triage reports daily during launch week. Treat data loss, broken restoration,
startup failures and invalid signatures as release blockers. Stop promoting
an affected build, mark the issue visibly and provide a tested recovery path.
Report resolved and remaining issues in every subsequent beta's notes.
Measure successful first sessions, completed workflows and actionable reports;
download counts alone do not measure active testers. Add no telemetry for this
launch. Proceed to final only when blocker reports are resolved and the
supported matrix, migration and rollback all pass.

## Communication sequence and drafts

Timing is relative to a qualified build, not a promised calendar date.

**First: Nadine.** Thierry's separate conference email comes before the public
campaign. Conference participation or endorsement must not be implied in posts.

**Teaser, roughly one week before launch:** one screenshot or 15–30 second clip
of Setup → template project → a reviewed font operation. Use a visible
“BETA” label. Post on social accounts and, where appropriate, the Glyphs forum's
[Plug-ins category](https://forum.glyphsapp.com/c/plug-ins/16).

> I'm preparing a beta of Glyphs MCP 2: a native Mac app for connecting AI
> assistants to Glyphs 4, managing components and starting font projects from
> templates. The beta will be open to everyone, with an optional group for
> people who want to help test it. More soon.

**Launch day:** GitHub prerelease and beta guide first; then one forum post and
short social announcement linking to the guide. Replace `[beta guide]` with the
verified public branch URL at posting time.

Forum title: **Glyphs MCP 2.0.0 Beta — open for testing**

> Glyphs MCP 2.0.0 Beta 4 is available to try. Setup now combines server status,
> Glyphs components and Codex, Claude Code, Claude Desktop and Cursor
> connections with inline progress. A dedicated window collects redacted
> installer, server and sidecar diagnostics.
>
> This is a beta. Please begin with a copy of a font and read the compatibility
> notes. Downloads are open; joining the tester group is optional. I'd especially
> welcome reports about fresh/update/removal installation, each agent connection,
> ownership conflicts, troubleshooting logs, project templates and a small
> review/apply/discard workflow.
>
> Download, setup and feedback: [beta guide]. Glyphs 3 remains on the separate
> 1.11.0 release.

Social draft:

> Glyphs MCP 2.0.0 Beta is ready to try: one native Setup for Glyphs 4 components,
> server controls and Codex, Claude Code, Claude Desktop and Cursor connections.
> Open download, optional tester group.
> I'd love to hear how your first session goes. [beta guide]

**Three days later:** answer recurring setup questions in the guide and share
one concrete workflow demonstration. **After one week:** publish a short
feedback update, known issues and what is planned for Beta 5. Thank testers
publicly only with their permission. Avoid a fixed update cadence until the
first feedback volume is known.

## Draft GitHub release notes

**Glyphs MCP 2.0.0 Beta 4 · build 46**

This fourth beta hardens and completes the Project visual glyph diff. It uses
one identity-verified schema-3 reader, supports quadratic contours,
decomposed components and open paths, and matches segments independently of
contour order. Component references receive an appearance-aware 8% neutral
fill while native paths remain unfilled. Holding Space shows a black silhouette
in light mode and a white silhouette in dark mode. Per-layer warnings preserve
usable previews, and fatal outline failures still fall back to Text.

The app retains the unified Setup, serialized component and connection
management, verified Cursor plugin and dedicated redacted troubleshooting logs
introduced in Beta 3.

The desktop requires macOS 14. Its payload is now Glyphs 4-only; Glyphs 3
continues through the separate v1.11.0 release. The seven-tool MCP interface
and bridge protocol are unchanged.

Signed update acceptance passed on an Apple-silicon VirtualBuddy guest running
macOS 26.6.2 and Glyphs 4.1 (4107): a notarized build-45 fixture discovered,
downloaded, verified, installed and relaunched build 46, after which Update All
migrated the components and Setup returned Ready. The previous Beta 3 app was
retained as a timestamped backup. Physical Intel acceptance and the remaining
manual scenario matrix are still open and are disclosed in BETA.md.

Candidate SHA-256 values:

```text
09c12429a49339627a167de7e3df040f7f6ece6495fea299942bb4671d175715  Glyphs-MCP-2.0.0-beta.4.dmg
0ef5b1eb17d3b0c67d9eb78ec0669ff91b0871629b6a7ace8f660dda8d50be35  Glyphs-MCP-2.0.0-beta.4.zip
d5c33763a8d1439fc765d703c188e93117b81ade3a34287400cc78b6df9aa406  appcast.xml
```

See BETA.md for open downloads, optional enrollment, known limitations and
the issue-report template.

## Beta 2 local preparation record — 16 September 2026

- The hybrid native/Pierre/SVG implementation is complete. The complete local
  gate passed with 1,930 Python tests (2 optional skips), all 189 macOS tests,
  deterministic ARM64/Intel payloads, the documentation production build and
  a fresh unsigned app verification.
- The visible app check covered the two-pane hierarchy, filtering, file status,
  Pierre source diff, accessible file buttons and safe glyph Text fallback.
  The Glyphs 4 worker also returned real decomposed glyph geometry through the
  installed private runtime.
- The detailed evidence and remaining signed-distribution gates are recorded
  in [BETA2-VALIDATION.md](BETA2-VALIDATION.md).
- The preparation record above was followed by a separate publication gate.
  Commit `42eb72b` and its signed `v2.0.0-beta.2` tag were pushed only to
  `lit/v2-beta`. The app and DMG were signed, notarized, stapled and accepted by
  Gatekeeper; the guarded publisher reran the full suite before uploading.
- The versioned DMG, Sparkle ZIP, signed appcast and checksums were published as
  a non-Latest prerelease. Stable Latest remains `v1.11.0`, and `main` was not
  changed.
- A packaging-only follow-up corrected Finder icon placement in the DMG. The
  script now applies positions to the icon-view window and fails unless they
  persist after closing and reopening it. The signed app payload and release
  tag were unchanged; the replacement DMG was notarized, visually checked and
  passed the complete local release suite before publication.

## Beta 1 preparation record — 8 September 2026

- 64 targeted Python tests passed, including beta identity, draft/public asset
  checks, version drift, deterministic lean payloads and desktop packaging.
- All 167 macOS installer tests passed in a fresh unsigned build.
- Documentation production build, source whitespace checks, shell syntax and
  lean package checks passed. Bundled and branch registries agree.
- Built app metadata matches 2.0.0 Beta 1, build 43. Components was opened and
  its beta title and version label were verified in the native app.
- No commits, pushes, tags, signing, notarization, uploads or communication
  publication were performed. The beta branch and feeds are prepared locally.
  Full release qualification, signed updates, cross-machine testing and public
  registry/feed verification remain before distribution.
