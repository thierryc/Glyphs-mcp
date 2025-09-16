.. function:: characterForGlyph(glyph)

		The (internal) character that is used in the edit view. It the glyph has a unicode, that is used, otherwise a temporary code is assigned. That can change over time, so don’t rely on it. This is mostly useful for constructing a string for see :attr:`tab.text <GSEditViewController.text>`

		.. versionadded:: 3.1
