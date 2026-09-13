# P12 lean candidate checkpoint

This local checkpoint preserves the tested private lean v2 runtime, ten managed skills and packaged mirrors (including the offline KDB), supporting packaging/installation scripts, regression tests and P12 evidence. It does not publish a release or absorb unrelated desktop/website migration work.

The previous product checkpoint contained the crash-guidance commit only. This commit makes the tested runtime and skill sources available in the actual `lit/v2-beta` source branch. Xcode changes are limited in the index to coordinated product version 2.0.0 and installer build 43; the user's other project-file changes remain in the working tree.

Validation: 561 lean regression checks pass. Two tests required loopback permission; isolated staged-tree validation identified and then resolved missing command-reference/roadmap dependencies. Its rebuilt bridge and sidecar exactly match the installed initialization-time fingerprints in `candidate-manifest.json`. No installation/restart/build publication occurred.

P12 currently has complete primary benchmark counts but remaining native qualification. With the same removed-plugin configuration, autosaving enabled reproduced the native crash. A single explicitly authorized pause completed 291 exact layer applications/restorations; autosaving was restored to eight seconds within 172.782 seconds and the process survived over 130 seconds afterward. This supports an autosave trigger, not a verified fix. P13 has not started.

## Evidence archive

`p12-evidence.tar.gz` contains all existing P12 reports, fixtures, native proofs, call logs, crash reports, scripts, the coverage index and the connection-harness dependency at their original repository-relative paths. Generated Python caches are excluded. `evidence-manifest.json` contains every member's size/SHA-256 and the archive hash. All 1,739 members were read back and verified. The original working files remain unchanged.

To review full evidence in a fresh local directory:

```sh
mkdir evidence
tar -xzf p12-evidence.tar.gz -C evidence
```

Latest report: `evidence/reports/v1-v2/12-slant/autosave-off-after-removal-20260913/report.md`.
Normal-autosave comparison: `evidence/reports/v1-v2/12-slant/without-speedpunk-20260913/report.md`.

Full desktop release readiness is not asserted. Native cubic Undo/Redo, dependent bounds, the independent input bound and native responsiveness remain the next P12 checks; any new crash stops the affected trial. Autosaving stays enabled unless a separate bounded pause is expressly authorized.
