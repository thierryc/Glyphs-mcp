**Functions**

	.. function:: generate([format, fontPath, autoHint, removeOverlap, useSubroutines, useProductionNames, containers, decomposeSmartStuff])

		Exports the instance. All parameters are optional.

		:param str format: The format of the outlines: :const:`OTF` or :const:`TTF`. Default: OTF
		:param str fontPath: The destination path for the final fonts. If None, it uses the default location set in the export dialog
		:param bool autoHint: If auto hinting should be applied. Default: True
		:param bool removeOverlap: If overlaps should be removed. Default: True
		:param bool useSubroutines: If to use subroutines for CFF. Default: True
		:param bool useProductionNames: If to use production names. Default: True
		:param list containers: list of container formats. Use any of the following constants: :const:`PLAIN`, :const:`WOFF`, :const:`WOFF2`. Default: PLAIN
		:param bool decomposeSmartStuff: If smart components should be decomposed. Default: True
		:return: On success, True; on failure, error message.
		:rtype: bool/list

		.. code-block:: python
			# export all instances as OpenType (.otf) and WOFF2 to user’s font folder

			exportFolder = '/Users/myself/Library/Fonts'

			for instance in Glyphs.font.instances:
			    instance.generate(FontPath=exportFolder, Containers=[PLAIN, WOFF2])

			Glyphs.showNotification('Export fonts', 'The export of %s was successful.' % (Glyphs.font.familyName))
