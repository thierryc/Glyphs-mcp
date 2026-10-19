"""Experimental helpers; never imported by the production runtime."""
from contextlib import contextmanager


VARIANTS = {"baseline": (False, False), "batching-only": (True, False),
            "suppression-only": (False, True), "combined": (True, True)}


def validate_child_environment(output, environment, process_group):
    if (environment.get("GLYPHS_MCP_SIDEBAR_REPORT_DIR") != str(output.parent)
            or not environment.get("GLYPHS_MCP_SIDEBAR_PARENT_PGID")
            or environment["GLYPHS_MCP_SIDEBAR_PARENT_PGID"] == str(process_group)):
        raise RuntimeError("Native probe requires the supervisor's isolated process group")


def value(owner, name):
    result = getattr(owner, name)
    return result() if callable(result) else result


def flag(owner, name):
    result = value(owner, name)
    if not isinstance(result, (bool, int)) or result not in (False, True):
        raise ValueError("Unavailable Boolean: " + name)
    return bool(result)


class RestorationError(RuntimeError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Sidebar flag restoration failed: " + repr(errors))


class CountGuard:
    """Preflight every owner/accessor before setting flags; restore exact values."""
    def __init__(self, items, font, selected=(), identity=id):
        self.rows, self.errors = [], []
        self.active = False
        selected = {identity(item) for item in selected}
        seen = set()
        for item in items:
            key = identity(item)
            if key in seen:
                continue
            seen.add(key)
            if value(item, "predicate") is None:
                continue
            if identity(value(item, "font")) != identity(font):
                raise ValueError("Sidebar item is not owned by the disposable font")
            original = flag(item, "isSuppressingCount")
            if not callable(getattr(item, "setSuppressCount_", None)):
                raise ValueError("Sidebar suppression setter unavailable")
            if key not in selected:
                self.rows.append((item, original))
        if not self.rows:
            raise ValueError("No unselected, owned predicate items to qualify")

    def start(self):
        if self.active:
            raise RuntimeError("Count guard is already active")
        self.active = True
        try:
            for item, _ in self.rows:
                item.setSuppressCount_(True)
                if not flag(item, "isSuppressingCount"):
                    raise RuntimeError("Suppression setter did not take effect")
        except BaseException:
            self.restore()
            raise

    def restore(self):
        if not self.active:
            return
        errors = []
        for index, (item, original) in enumerate(self.rows):
            try:
                item.setSuppressCount_(original)
                if flag(item, "isSuppressingCount") != original:
                    raise RuntimeError("Restored flag differs from original")
            except BaseException as error:
                errors.append({"index": index, "error": str(error)})
        self.active = False
        self.errors.extend(errors)
        if errors:
            raise RestorationError(errors)


@contextmanager
def interface_batch(font, enabled):
    original = flag(font, "isUpdateInterfaceEnabled")
    for name in ("disableUpdateInterface", "enableUpdateInterface"):
        if not callable(getattr(font, name, None)):
            raise ValueError("Interface accessor unavailable: " + name)
    changed = enabled and original
    if changed:
        font.disableUpdateInterface()
    try:
        yield
    finally:
        if changed:
            font.enableUpdateInterface()
        if flag(font, "isUpdateInterfaceEnabled") != original:
            raise RuntimeError("Interface state was not restored")


def classify(runs, repeats):
    expected = {(name, repeat) for name in VARIANTS for repeat in range(1, repeats + 1)}
    measured = {(r.get("variant"), r.get("repeat")) for r in runs}
    if measured != expected or len(runs) != len(expected):
        return "failed or blocked"
    if any(r.get("outcome") not in {"passed", "alert"} for r in runs):
        return "failed or blocked"
    baseline = [r for r in runs if r["variant"] == "baseline"]
    if not any(r["outcome"] == "alert" for r in baseline):
        return "not reproduced" if all(r["outcome"] == "passed" for r in runs) else "failed or blocked"
    guarded = [name for name in ("suppression-only", "combined")
               if all(r["outcome"] == "passed" for r in runs if r["variant"] == name)]
    return "promising mitigation" if guarded else "failed or blocked"
