.. attribute:: properties
		Holds the fonts info properties. Can be instances of :class:`GSFontInfoValueSingle` and :class:`GSFontInfoValueLocalized`

		The localized values use language tags defined in the middle column of `Language System Tags table`: <https://docs.microsoft.com/en-us/typography/opentype/spec/languagetags>.

		The names are listed in the constants: `Info Property Keys`_

		.. code-block:: python
			# To find specific values:
			instance.propertyForName_(name)
			# or
			instance.propertyForName_languageTag_(name, languageTag).

			# To add an entry:
			instance.setProperty_value_languageTag_(GSPropertyNameFamilyNamesKey, "SomeName", None)

		:type: list

		.. versionadded:: 3
