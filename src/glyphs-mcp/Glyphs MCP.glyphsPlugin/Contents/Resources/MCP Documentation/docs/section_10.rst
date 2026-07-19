.. attribute:: defaults

		A dict like object for storing preferences. You can get and set key-value pairs.

		Please be careful with your keys. Use a prefix that uses the reverse domain name. e.g. :samp:`com_MyName_foo_bar`.

		:type: dict

		.. code-block:: python
			# Check for whether or not a preference exists
			if "com_MyName_foo_bar" in Glyphs.defaults:
			    # do stuff

			# Get and set values
			value = Glyphs.defaults["com_MyName_foo_bar"]
			Glyphs.defaults["com_MyName_foo_bar"] = newValue

			# Remove value
			# This will restore the default value
			del Glyphs.defaults["com_MyName_foo_bar"]
