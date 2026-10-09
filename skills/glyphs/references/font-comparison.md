# Compare compiled fonts

Use `compare_fonts` for explicit local compiled static/variable TTF inputs.
This workflow needs the sidecar and optional managed Diffenator runtime; it
does not require Glyphs to be running, a document ID, a saved live font, or Save.

Verify the specific connection with `get_status`, requiring
`font.compare.diffenator.v1` in `comparisonCapabilities`. Read
`comparisonWorker.error` for installation failures. Install the optional runtime
through Setup when its signed distribution is available; preserve an unavailable
capability as an installation gap.

Call `compare_fonts(baseline_files, candidate_files, options)` with 1–32 absolute
existing TTF files on each side, each at most 32 MiB. Choose the baseline explicitly
from a release or retained export. Coordinate candidate export separately through
the existing export workflow; compilation settings should match and be recorded.

`options.styles` defaults to `instances`. `masters` and `cross_product` require
one variable TTF on each side; cross_product uses min/default/max, compatible
axis tags/ranges and at most 256 locations. Optional `filterStyles` is a style-name
regex. `userWordlist` is an absolute `.txt`/`.csv` file up to 1 MiB, supporting
script/language/feature settings. Unmatched or duplicate named styles fail.

Retain the job ID and poll `get_job(include_preview=false)` for actual stages.
Open its local HTML `entryPoint` when ready. Summarize measured report evidence
and selected coverage; successful completion does not establish visual quality
or exhaustive feature coverage. Report export settings as unknown when absent.

Inputs are privately snapshotted and hashed. `discard_job` cancels preparation
and releases private artifacts. With report-retention authorization,
`accept_job` publishes to an absolute new directory, verifying compiled-input
and report hashes. Existing destinations are refused. Comparison jobs have no
live mutation, cannot use `apply_job`, and never save a font. Reconcile an
uncertain publication through its original job instead of repeating the work.
