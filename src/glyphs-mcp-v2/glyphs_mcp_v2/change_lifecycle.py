"""Save lifecycle for the per-save change graph."""

from __future__ import annotations

from .change_history import ChangeHistory


class DocumentHistoryLifecycle:
    def __init__(self, history: ChangeHistory) -> None:
        self._history = history

    def document_was_saved(
        self,
        document_id: str,
        *,
        make_copy: bool = False,
        succeeded: bool = True,
    ) -> bool:
        if not document_id or make_copy or not succeeded:
            return False
        self._history.reset_after_save(document_id)
        return True


__all__ = ["DocumentHistoryLifecycle"]
