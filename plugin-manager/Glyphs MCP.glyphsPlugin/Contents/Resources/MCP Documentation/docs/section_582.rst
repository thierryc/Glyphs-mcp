.. function:: PickGlyphs(content=None, masterID=None, searchString=None, defaultsKey=None):

	AskString Dialog

	:param content: a list of glyphs from with to pick from (e.g. filter for corner components)
	:param masterID: The master ID to use for the previews
	:param searchString: to pre-populate the search
	:param defaultsKey: The userdefaults to read and store the search key. Setting this will ignore the searchString

	:return: the list of selected glyphs and
	:rtype: tuple(list, str)

	.. versionadded:: 3.2
