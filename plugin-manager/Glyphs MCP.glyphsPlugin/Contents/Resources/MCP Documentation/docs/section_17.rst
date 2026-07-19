.. attribute:: scriptAbbreviations
		A dictionary with script name to tag mapping, e.g., 'arabic': 'arab' or 'devanagari': 'dev2'

		:type: dict

		.. code-block:: python
			scriptTag = Glyphs.scriptAbbreviations["devanagari"]
			print(scriptTag) -> "dev2"
