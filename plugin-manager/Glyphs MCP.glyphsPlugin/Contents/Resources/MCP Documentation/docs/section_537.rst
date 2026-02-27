.. attribute:: key
		the key

		:type: str

	.. code-block:: python
		# GSFontInfoValueSingle is stored in e.g. font.properties
		# one of the differences between GSFontInfoValueSingle and GSFontInfoValueLocalized
		# is that the first doesn't have "values" attribute
		for fontProperty in font.properties:
		    if not hasattr(fontProperty, "values"):
		        print(fontProperty.key)
