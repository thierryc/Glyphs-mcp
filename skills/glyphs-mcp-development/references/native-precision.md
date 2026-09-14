# Precise native coordinate edits

Project qualification: Glyphs 4.1 (4107), isolated native CLI trials RV01
T04–T08. Integer-grid rounding changed a requested +2.5 handle move to +3 and a
102.5 midpoint to 103. Native extrema and cubic subdivision also changed drawn
geometry until the temporary layer rounding flag was protected. This selector
is native evidence, not a documented guarantee for every Glyphs 4 build.

Resolve all intended glyphs and exact ordinary master IDs before writing. An
all-master request means every ordinary master of that explicitly bound font;
validate missing layers and operation-specific correspondence first. Do not
include backup, intermediate or alternate layers by iterating all stored layers.
Preserve the font's grid settings.

For a bounded operation on already validated `target_layers`, use the existing
native flag and restore its previous value, including when it was already true:

```python
from contextlib import ExitStack

states = []
for layer in target_layers:
    getter = getattr(layer, "temporarilyDisableRounding", None)
    setter = getattr(layer, "setTemporarilyDisableRounding_", None)
    if getter is None or not callable(setter):
        raise RuntimeError("Native precision API unavailable on this host")
    previous = bool(getter() if callable(getter) else getter)
    states.append((layer, previous))

with ExitStack() as restore:
    for layer, previous in states:
        restore.callback(layer.setTemporarilyDisableRounding_, previous)
        layer.setTemporarilyDisableRounding_(True)
    perform_requested_operation(target_layers)

for layer, previous in states:
    getter = layer.temporarilyDisableRounding
    assert bool(getter() if callable(getter) else getter) == previous
verify_exact_requested_values(target_layers)
```

`ExitStack` attempts every registered restoration even if one fails. A failed
operation propagates after restoration; flag restoration is **not rollback**.
Record partial edits or a restoration error. If the API is unavailable, stop
the precision operation before writing and identify the unsupported host/API;
do not silently round or change font grid settings.

Read back exact requested coordinates after restoration. For computed geometry,
state a numerical tolerance separately; native compatibility and equal node
counts do not establish equal curves or good interpolation. Verify the relevant
widths, anchors, components, metadata and surviving native objects. Test failures
on disposable fonts; existing native Undo behavior remains unchanged. Do not
import bridge internals or construct a new topology or recovery framework.

Evidence: RV01, commit `a833e599`, `reports/rv01-realistic-20260914`,
T04–T08 and `artifacts/outline_tasks.py`. The instructions above are
self-contained; that repository evidence is supplemental.
