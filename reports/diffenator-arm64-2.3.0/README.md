# Diffenator arm64 candidate for 2.3.0

This is fresh evidence for archive `diffenator-arm64-r1.zip`, SHA-256
`7ea63a23a9e529187f410d16d73f8019d95792509af2600663e8342001de282a`,
114,874,753 bytes. It does not inherit historical runtime acceptance.

The exact pinned source revision was rebuilt with CPython 3.11.16, Unicode
17.0.0 and the locked dependency wheels. GitHub’s source archive bytes differed
from the historical hash; all 107 regular files matched `git archive` of the
pinned commit before a new source wheel was built. See the source audit and
build-tool receipt. The new wheel hash is recorded in the input lock.

Apple accepted notarization submission `2850637d-73f1-4e49-a6f9-0dd662d949a3`.
On the Apple Silicon macOS 26.7.1 host, all nine comparison cases passed with
network access denied. Production installer trust checks verified all 81 native
subjects, including expected signing team and Gatekeeper acceptance. Managed
install, update, remove, reinstall, relocation, cancellation and create-only HTML
publication passed in disposable directories. Only download transport was
redirected to the already verified local ZIP; ownership, extraction, signing,
Gatekeeper, transactions and comparison services were real production code.
No working Glyphs document or component installation was changed.

## Remaining blockers

- The macOS 14.6.1 VirtualBuddy VM was not available for this run. Its availability
  is awaiting user confirmation. No guest result or minimum OS qualification is claimed.
- The license audit retained files from 44 of 45 wheel inputs. `youseedee 0.7.0`
  lacks a license file in both its wheel and exact upstream tag; its license
  metadata contains README usage text. See `license-audit.json`. The license
  bundle cannot be declared complete until redistribution terms are established.
- No optional-runtime release was published; anonymous public download has not
  been verified. The production Diffenator catalog remains disabled.
- The exact signed desktop 2.2.0 → 2.3.0 upgrade and final release gates remain.

Intel Diffenator support is excluded. The desktop app remains universal.
Host results retain their scope; final distribution is not qualified.
