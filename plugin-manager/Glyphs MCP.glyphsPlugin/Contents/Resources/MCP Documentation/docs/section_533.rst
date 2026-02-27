.. attribute:: key
		the key

		:type: str

	.. code-block:: python
		# searching for GSFontInfoValueLocalized with given "designers" key
		for fontInfo in font.properties:
		    if fontInfo.key == "designers":
		        print(fontInfo)
