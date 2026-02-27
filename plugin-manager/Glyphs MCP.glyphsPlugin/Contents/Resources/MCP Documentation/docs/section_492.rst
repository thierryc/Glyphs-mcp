.. attribute:: text
		The text of the tab, either as text, or slash-escaped glyph names, or mixed. OpenType features will be applied after the text has been changed.

		:type: str

		.. code-block:: python
			string = ""
			for l in font.selectedLayers:
			    string += "/"+l.parent.name
			tab = font.tabs[-1]
			tab.text = string
