.. attribute:: string
		The plain underlying string of the tab

		:type: str

		.. code-block:: python
			string = ""
			for l in font.selectedLayers:
			    char = font.characterForGlyph(l.parent)
			    string += chr(char)
			tab = font.tabs[-1]
			tab.text = string

		.. versionadded:: 3.2
