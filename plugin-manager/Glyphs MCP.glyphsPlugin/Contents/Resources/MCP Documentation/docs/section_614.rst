.. function:: PickGlyphs(content=None, masterID=None, searchString=None, defaultsKey=None)

	Shows a dialog to select a glyph and returns the selected glyphs.

	:param content: a list of glyphs from with to pick from (e.g. filter for corner components)
	:param masterID: The master ID to use for the previews
	:param searchString: to pre-populate the search
	:param defaultsKey: The userDefaults to read and store the search key. Setting this will ignore the searchString

	:return: the list of selected glyphs and the typed search string
	:rtype: tuple(list, str)

	.. versionadded:: 3.2
