.. attribute:: defaultValue
		the value that is considered the default (either the dflt or English entry)

		:type: str

	.. code-block:: python
		# prints the default value for given GSFontInfoValueLocalized instance
		print(fontInfoValueLocalized.defaultValue)

		# The print below will always return True, because
		# font.designer represent the same value

		fontInfoValueLocalized = None
		for fontInfo in font.properties:
		    if fontInfo.key == "designers":
		        fontInfoValueLocalized = fontInfo

		print(fontInfoValueLocalized.defaultValue == font.designer)
