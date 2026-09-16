# Glyphs MCP 2.0.0 Beta 2 — release and launch plan

## Decision

Prepare **2.0.0 Beta 2**, tag `v2.0.0-beta.2`, build **44**, on `lit/v2-beta`.
Keep all v2 application and registry work off `main` through the beta cycle.
Use an open download with optional enrollment. Focus communication on the
Glyphs forum, GitHub and Thierry's social accounts. Thierry handles the first
email to Nadine separately; no email or announcement has been sent.

The public promise is a beta to try and help improve. Avoid “2.0 is released,”
“production ready,” or guaranteed dates for a final release.

## Distribution

- Use a GitHub **prerelease**, titled **Glyphs MCP 2.0.0 Beta 2**. Keep
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
  increasing: 44, 45, 46… even though the marketing version was renumbered.
  Update signatures and build ordering follow the
  [Sparkle publishing model](https://sparkle-project.org/documentation/publishing/).
- Preserve the service identity. Qualify upgrades and rollback, including
  restored settings and component receipts; do not market side-by-side server
  isolation. Glyphs 3 remains pinned to 1.11.0.

## Release sequence

1. Review the full accumulated worktree, including the UI fixes, and run the
   complete local release gates. Confirm lean payload reproducibility, hashes,
   Python and macOS tests, documentation and private runtime checks.
2. Test disposable fonts and the installer on Apple silicon and Intel, minimum
   and current macOS, with the actual supported Glyphs 4 builds. Cover fresh
   install, upgrade, component removal, preserved settings, rollback, native
   Save/Undo/Redo/discard, templates online/offline, window resizing and dark mode.
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
   ./scripts/publish_release_assets.sh --tag v2.0.0-beta.2 --publish --confirm-publish v2.0.0-beta.2
   ```

6. Verify the exact public download and checksum, then commit the exact signed
   appcast bytes to the beta branch. Verify both raw registry/feed URLs from a
   clean machine. Replace BETA.md's preparation notice with the verified
   release link and tested compatibility/rollback instructions.
7. Confirm GitHub's stable Latest release still identifies the previous stable
   release. Publish the communication below only after the beta download works.

Beta 3 uses `--beta 3` and a higher installer build. Final 2.0.0 gets a new
higher build and tag, final qualification, and a separately reviewed merge to
`main`. Do not relabel Beta 2 as final or repoint its tag.

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
of Components → template project → a reviewed font operation. Use a visible
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

> Glyphs MCP 2.0.0 Beta 2 is available to try. It adds a two-pane, read-only Git
> diff browser with syntax-highlighted source diffs and visual before/after
> overlays for glyphs inside `.glyphspackage` sources. The existing component,
> project and review workflows remain available for Glyphs 4.
>
> This is a beta. Please begin with a copy of a font and read the compatibility
> notes. Downloads are open; joining the tester group is optional. I'd especially
> welcome reports about source and visual glyph diffs, installation, connecting
> your AI client, project templates and a small review/apply/discard workflow.
>
> Download, setup and feedback: [beta guide]. Glyphs 3 remains on the existing
> 1.11.0 plugin.

Social draft:

> Glyphs MCP 2.0.0 Beta is ready to try: a native Mac app for Glyphs 4, component
> management and project templates. Open download, optional tester group.
> I'd love to hear how your first session goes. [beta guide]

**Three days later:** answer recurring setup questions in the guide and share
one concrete workflow demonstration. **After one week:** publish a short
feedback update, known issues and what is planned for Beta 3. Thank testers
publicly only with their permission. Avoid a fixed update cadence until the
first feedback volume is known.

## Draft GitHub release notes

**Glyphs MCP 2.0.0 Beta 2 · build 44**

This second beta adds a two-pane, read-only Git browser. Text files use
syntax-highlighted unified or split diffs; changed glyphs inside
`.glyphspackage` sources add Visual/Text switching with layer selection and
near-black current geometry, mint reference changes and a cyan delta fill.
Holding Space shows a pure-black silhouette. The app loads selected files on demand and
does not expose editing, comments, staging or commit actions.

The desktop now requires macOS 14. Glyphs 3 continues to use 1.11.0, and the
seven-tool MCP interface and bridge protocol are unchanged.

Before publication, insert the tested macOS/Glyphs compatibility table,
verified installation and rollback steps, actual known issues and checksums.
Link to BETA.md for open downloads, optional enrollment and reports. Do not
publish these notes with unresolved placeholders.

## Beta 2 local preparation record — 16 September 2026

- The hybrid native/Pierre/SVG implementation is complete. The complete local
  gate passed with 1,929 Python tests (2 optional skips), all 189 macOS tests,
  deterministic ARM64/Intel payloads, the documentation production build and
  a fresh unsigned app verification.
- The visible app check covered the two-pane hierarchy, filtering, file status,
  Pierre source diff, accessible file buttons and safe glyph Text fallback.
  The Glyphs 4 worker also returned real decomposed glyph geometry through the
  installed private runtime.
- The detailed evidence and remaining signed-distribution gates are recorded
  in [BETA2-VALIDATION.md](BETA2-VALIDATION.md).
- No commit, push, tag, signing, notarization, upload or publication was
  performed.

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
