.. attribute:: value
		The value

		:type: str

	.. code-block:: python
		# GSFontInfoValue is stored in e.g. values attribute of font.properties
		for fontProperty in font.properties:

		    # not all of font.properties contains this attribute
		    # so we are going to look for those, that have it
		    if hasattr(fontProperty, "values"):
		        for fontInfoValue in fontProperty.values:
		            # this line prints out the value attribute of
		            # found GSFontInfoValue instance
		            print(fontInfoValue.value)
