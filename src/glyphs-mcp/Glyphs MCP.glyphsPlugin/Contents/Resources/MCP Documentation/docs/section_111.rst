.. function:: save([path=None, formatVersion=3, makeCopy=False])

		Saves the font.

		If no path is given, it saves to the existing location.

		:param path: (Optional) file path including filename and suffix. When the font is loaded directly (`GSFont(path)`), the path argument is required.
		:type path: str
		:param formatVersion: The format of the file. Requires `makeCopy=True`
		:type formatVersion: int
		:param makeCopy: saves a new file without changing the documents file paths. So it always need a `path` argument
		:type makeCopy: bool
