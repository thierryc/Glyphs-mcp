.. attribute:: properties
		Holds the fonts info properties. Can be instances of :class:`GSFontInfoValueSingle` and :class:`GSFontInfoValueLocalized`

		The localized values use language tags defined in the middle column of `Language System Tags table`: <https://docs.microsoft.com/en-us/typography/opentype/spec/languagetags>.

		To find specific values, use master.propertyForName_(name) or master.propertyForName_languageTag_(name, languageTag).

		:type: list

		.. versionadded:: 3
