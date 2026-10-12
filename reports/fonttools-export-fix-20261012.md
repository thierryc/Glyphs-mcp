# Default Glyphs Python export fix

Date: October 12, 2026. Local candidate only; no commit, release or host runtime
installation was performed. Existing Python-detection and Setup changes remain
in this candidate.

## Cause and change

Export generation and verification previously ran together in the external
Glyphs Python interpreter. The official Glyphs module does not ship FontTools
or HarfBuzz, although the managed private MCP runtime bundles them.

Native generation now returns bounded generation evidence explicitly marked
unverified. The private MCP interpreter inspects the staged files, verifies
OpenType tables and actual containers, runs requested shaping checks, and creates
the validated artifact manifest. Only then does the worker return a successful
artifact result. No extra packages are installed into Glyphs Python or python.org
Python. Existing file limits, symlink rejection, container checks, source-bound
publication and cancellation before returning verified artifacts are retained.

## Automated checks

124 focused Python tests passed across export/compile, worker errors, sidecar,
protocol, installation, payload build and desktop build checks. Six new cases
exercise generation with verifier imports blocked, successful plain/WOFF2
verification, corrupt binary rejection, wrong-container rejection, mismatched
native document evidence, and cancellation after verification. Failure cases
retain unverified evidence and do not return a successful artifact.
`git diff --check` is clean.

## VM qualification

Guest: Copy of glyphs-base at <vm-address>, verified VirtualMac2,1 and NIC
<vm-nic>. Glyphs 4.1.1/build 4108, default Glyphs Python 3.14.6;
private MCP Python 3.14.7. The idle service stopped and Glyphs quit with no open
fonts before installation. The prior manager app was retained in the guest's
recovery folder.

The updated candidate was installed normally, and installed worker, native
worker and export module bytes were compared with the candidate payload and
current source. Native execution confirms the selected official module prefix
and that neither FontTools nor HarfBuzz is available in that interpreter.
Production `GlyphsCliWorker.prepare` then successfully generates and verifies
all six static outputs below using the private runtime.

| Native format | Container | Glyph count | Tables | Shaping and control |
| --- | --- | --- | --- | --- |
| TTF | plain | 3 | Passed | Passed |
| TTF | woff | 3 | Passed | Passed |
| TTF | woff2 | 3 | Passed | Passed |
| OTF | plain | 3 | Passed | Passed |
| OTF | woff | 3 | Passed | Passed |
| OTF | woff2 | 3 | Passed | Passed |

The disposable normalized format-4 source hash is unchanged. Final worker
results and reports are persisted with successful verification evidence. No
user font was edited. Variable-font exports and physical Intel execution were
not newly qualified in this task.

The first live status check timed out before any fixture Open or export job was
dispatched. A bounded read-only check subsequently succeeded. The retained test
then completed successfully: loaded bridge/sidecar identities matched the
installation receipt; a TTF/plain/WOFF/WOFF2 job reached verified artifact-ready
state and was published to a new directory; every published file hash matched
its manifest. A separate OTF job was discarded and its private staging was
removed. The source remained unchanged, and the fixture closed cleanly with
unsaved_changes=refuse. No hanging UI automation was used.

## Local app

- App: `dist/local/Glyphs MCP.app` (also opened for manual testing).
- ZIP: `dist/local/Glyphs-MCP-fonttools-fix-local.zip`.
- Unsigned Debug candidate retaining 2.0.3/build 59; not a published release.
- Build time: 2026-10-12T12:10:01.939927+00:00.
- Source SHA-256: `35a79ba44ff92dbea0f8213ea5c44120d0a3837f26b105e936032079a6defdfd`.
- App SHA-256: `918d597694c6d7210a6670a29f6f9433f69c0d55e3bbf2d509ac3bd626843d30`.
- ZIP SHA-256: `9c22c76ed78534dd73573e219c4a844703416c1c2e80bdb5d65f61b76e13ddfd`.

Both current source and the complete app match the build receipt. Raw VM reports
are retained under `build/vm-export-fix-20261012/`; test inputs, recovery apps
and disposable fonts remain under the guest's `~/Desktop/GlyphsPythonFreshTest`.
