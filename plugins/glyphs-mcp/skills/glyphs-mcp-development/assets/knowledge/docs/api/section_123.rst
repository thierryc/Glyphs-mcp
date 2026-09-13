.. function:: close([ignoreChanges=True])

		Closes the font.

		:param ignoreChanges: Optional. Ignore changes to the font upon closing
		:type ignoreChanges: bool

	.. function:: disableUpdateInterface()

		Disables interface updates and thus speeds up glyph processing. Call this before you do big changes to the font, or to its glyphs. Make sure that you call :meth:`font.enableUpdateInterface() <GSFont.enableUpdateInterface()>` when you are done.

	.. function:: enableUpdateInterface()

		This re-enables the interface update. Only makes sense to call if you have disabled it earlier.
