.. attribute:: string

		The plain underlying string of the tab

		:type: str

		.. code-block:: python
			string = ""
			for layer in font.selectedLayers:
			    char = font.characterForGlyph(layer.parent)
			    string += chr(char)
			tab = font.tabs[-1]
			tab.text = string

		.. versionadded:: 3.2
