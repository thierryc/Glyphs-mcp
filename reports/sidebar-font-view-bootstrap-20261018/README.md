# Isolated Font View bootstrap investigation — October 18, 2026

The CLI blocker is explained. A protected, unmodified full-app copy reaches
native GUI startup and loads the diagnostic plug-in. The user subsequently
accepted its trial manually. The probe then failed while importing the shared
harness because GlyphsErr has no fileno; the test process is stopped. The
experimental child now handles that logging boundary (29 focused tests pass).
**Font View and count suppression remain unqualified.** At the user’s direction,
further isolation work uses VirtualBuddy; see ../sidebar-font-view-vm-20261018/.
The detailed protected-copy evidence below describes the earlier attempt.

## Findings

1. `glyphs run` loads the native frameworks but supplies its own `GSApplication`
   class and no app delegate. `GSLocalNumberFormatTransformer` and several Font
   View nib classes are absent: `GSImageFlowView`, `GSGlyphDetailView`,
   `GSFontListViewTableView`, `GSContentView`, and `GSContextOutlineView`.
   These classes reside in the app executable. Registering a display-number
   transformer alone advances nib loading, then fails with `NSView setDelegate:`.
   Loading the executable with NSBundle fails with Cocoa error 3584. More shims
   would change the UI being qualified rather than reproduce the full app.
2. A renamed/re-signed app copy exits before GUI startup. Inspection found native
   code-signature validation at the entry point. That check was not patched or
   bypassed. The final route preserves the installed Info.plist and executable
   byte-for-byte, including its original bundle identifier and signature.
3. The full app stalls in `NSString.stringByResolvingSymlinksAndAliases` when
   launched from `/private/tmp`. Native CLI probes time out resolving the copied
   app, home and support paths there; `/Applications/Glyphs 4.app` and the global
   Python framework resolve normally. Moving the app and its private home/temp
   paths under the checkout's physical `build/` path gets past this loop. This
   is a single-build observation, not a generic claim about all temporary paths.
4. `CFFIXED_USER_HOME` redirects home/support discovery but **alone does not
   isolate preferences**: the CLI still reads 209 keys from the working app's
   preference domain. A nested child sandbox that denies cfprefsd lookup and
   reads of working preferences produces an empty domain. The supervisor checks
   that result before starting the full GUI.
5. Home redirection alone also does not prevent fallback discovery of working
   plug-ins. An intermediate disposable run read installed plug-ins; its sandbox
   blocked user-directory writes and outbound connections. The final profile
   additionally denies reads of the original Glyphs support folders. Its log
   shows only the temporary diagnostic plug-in among user plug-ins.

## Final protected GUI attempt

Host: macOS 26.7.1, Glyphs 4.2 (4202). Disposable app PID 1797 was stopped by its
45-second watchdog. The diagnostic loader reports zero open fonts and the exact
copied app/private support paths. It never targeted a working font or issued an
MCP request to the installed server.

The test profile denies working preference/support reads, writes outside its
owned build fixture, Apple Events and network sockets. State restoration and
automatic updates are disabled through launch arguments. Original installed app
files are not edited, and no working app restart is performed. The temporary
probe uses the existing SDK loader; it is placed only in the disposable support
folder, not the working Plugins directory.

The GUI reaches two startup dialogs:

- Trial/registration: “I have read the license agreement.” and “Continue Trial”.
  Accepting terms requires the user's decision; neither checkbox nor button was
  changed. Do not suppress this dialog by inventing acceptance preferences.
- Plug-in Manager: “Problem parsing repository source error 123.” The network
  restriction is a likely cause, not a proven native error diagnosis. This is
  separate from the sidebar predicate alerts. It was not dismissed.

An observation timer records only this process's visible dialogs in modal run
loop mode. It does not close dialogs or run font edits while first launch waits.
The normal preflight callback cannot proceed through the pending modal startup.

## Next step

After the user elects to review/accept the license in the isolated instance,
relaunch the prepared signed-copy setup under its child sandbox and let the user
complete first launch. Keep the repository-source alert distinct from filter
alerts; no global alert suppression is acceptable. Then run the real Font View
preflight and only afterward enable the 20-run suppression matrix. Retain the
explicit document/owner checks and external process watchdog.

The prepared local launcher is `launch_probe.py`; it references `setup.json` and
requires macOS permission to create a nested sandbox. It is an investigation
artifact, not an installed launcher or a production runtime change. Its current
45-second timeout is intentionally noninteractive. Do not run it unsandboxed or
remove the isolation proof checks. Manual first-launch review needs a longer,
supervised window and explicit user participation. The prepared app is retained
in the ignored build directory; the report does not contain an app binary or
license credentials.

## Evidence

- `cli-inventory.json`, `cli-ui-classes.json`: runtime class/bundle observations.
- `numeric-display-only.json`: rejected narrow bootstrap and next native error.
- `path-resolution.json`, `temporary-path-startup-sample.txt.gz`: path-loop proof.
- `isolation-preflight.json`, `isolation.sb`: empty domain and final restrictions.
- `gui-loader.json`, `launch.json`: exact test process, source hashes and outcome.
- `startup-dialogs.json`: relevant modal text; recent-document lists excluded.
- `gui.stderr.log`, `probe-plugin.py`: final run diagnostics and observer source.
- `evidence-sha256.json`: evidence fingerprints at capture time.

No suppression matrix cases were executed. No change to production bridge,
sidecar, protocol or the previously qualified guidance is part of this turn.
