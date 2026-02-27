.. attribute:: defaults
		A dict like object for storing preferences. You can get and set key-value pairs.

		Please be careful with your keys. Use a prefix that uses the reverse domain name. e.g. :samp:`com.MyName.foo.bar`.

		:type: dict

		.. code-block:: python
			# Check for whether or not a preference exists
			if "com.MyName.foo.bar" in Glyphs.defaults:
			    # do stuff

			# Get and set values
			value = Glyphs.defaults["com.MyName.foo.bar"]
			Glyphs.defaults["com.MyName.foo.bar"] = newValue

			# Remove value
			# This will restore the default value
			del Glyphs.defaults["com.MyName.foo.bar"]
