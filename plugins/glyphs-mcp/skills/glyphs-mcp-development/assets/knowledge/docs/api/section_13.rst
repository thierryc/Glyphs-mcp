.. function:: registerDefaults(dictionary)
		give it a doct with key value pairs to set default values in the user defaults

		.. code-block:: python
			values = {
				"com_MyName_foo": 12,
				"com_MyName_bar": "foo",
			}
			Glyphs.registerDefaults(values)
