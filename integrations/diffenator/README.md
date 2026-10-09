# Optional Diffenator runtime

The adapter uses source revision `cecdab703d462cfea25b748b19ea4813d3f4d680`.
The compatibility profile records a private CPython **3.11.16** environment,
Unicode **17.0.0**, exact resolved dependencies and compiled-font fixture results.
This includes glyphsets 1.0.0; the older 0.6.5 dependency did not provide the
required import behavior. The adapter uses the pinned implementation directly,
avoiding Ninja command strings and automatic Unicode downloads.

Standalone qualification also found an implicit Setuptools dependency in
gflanguages. The lock explicitly includes Setuptools 79.0.1, supplying
`pkg_resources`; a development virtual environment had supplied it automatically.
`inputs-arm64.json` locks all 45 wheel inputs, Python and Unicode archives.
`provenance-arm64.json` records upstream URLs and independently verified registry
wheel hashes, plus the pinned source wheel and archive identity.

The profile establishes local Apple Silicon compatibility, not signed runtime,
Intel, minimum-OS, relocation or installed-app qualification.

## Build inputs and candidate

Prepare a JSON input lock containing `sourceRevision`, `pythonVersion`,
`unicodeVersion`, `architecture`, and `python`, `unicode`, `wheels`.
The latter contain relative `path` and exact `sha256` fields; `wheels` is an array.
Use a verified Python standalone archive, the pinned source-built Diffenator
wheel, every resolved dependency wheel, and the Unicode archive. Keep the source
archive hash and wheel build provenance beside the lock. Build offline:

```sh
python3 scripts/build_diffenator_runtime.py \
  --inputs /absolute/verified-inputs/inputs-arm64.json \
  --architecture arm64 --output build/diffenator/candidate-arm64
```

The builder checks all input hashes and dependency versions, dereferences Python
aliases, excludes bytecode caches, vendors Unicode data, and records the final
runtime file hashes. It emits a ZIP with its exact inventory and checksum.
An optional `--sign-identity` signs native files before sealing that inventory.
Rebuild after signing changes; signatures change executable hashes.

Apple Silicon candidate packages have been built locally, signed, accepted by
Apple notarization, and executed through all nine comparison fixtures. Public
assets and other platform gates remain separate. The exact signed arm64 runtime
also passed relocation to a temporary home, managed install/update/remove, a real
comparison and create-only report publication; all nine fixture comparisons
passed with network access denied. See [2.0.2 qualification](../../V2.0.2-RELEASE.md).

Run `scripts/qualify_diffenator_adapter.py` with the candidate's Python and
`share/diffenator-ucd`, using a new output directory. Qualify a relocated runtime,
offline execution, cancellation and signed native loading separately on each
architecture. Preserve dependency license files and provenance with the artifact.

## Enable managed distribution

Notarize the distribution and verify its actual signing team/Gatekeeper result.
Only then populate `integrations/optional-tools.json` with qualified status,
architecture-specific release asset URL, archive size/hash, payload root,
inventory, version, directory, team ID and trust subjects. Qualification must
include the Python executable and native dependencies; manifest claims alone
do not establish trust. Publishing those assets is a separate release action.

Until those assets exist, Setup presents the pending qualification explanation
and leaves installation disabled. The runtime does not modify the sidecar's
Python or Glyphs' scripting environment.
