.. attribute:: properties

		Holds the fonts info properties. Can be instances of :class:`GSInfoValueSingle` and :class:`GSInfoValueLocalized`.

		The localized values use language tags defined in the middle column of `Language System Tags table`: <https://docs.microsoft.com/en-us/typography/opentype/spec/languagetags>.

		The names are listed in the constants: `Info Property Keys`_

		.. code-block:: python
			# To access the default value:

			font.properties["versionString"]

			font.properties["versionString"] = "version 1.0"

			# To access specific languages:

			font.properties.getProperty(GSPropertyNameDesignersKey, "DEU")

			font.properties.setProperty(GSPropertyNameDesignersKey, "SomeName", "DEU")

		:type: list

		.. versionadded:: 3
