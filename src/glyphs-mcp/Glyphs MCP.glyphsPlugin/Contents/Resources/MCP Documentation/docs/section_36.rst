.. function:: localize(localization)

		Return a string in the language of Glyphs.app’s UI locale, which must be supplied as a dictionary using language codes as keys.

		The argument is a dictionary in the `languageCode: translatedString` format.

		You don’t need to supply strings in all languages that the Glyphs.app UI supports. A subset will do. Just make sure that you add at least an English string to default to next to all your other translated strings. Also don’t forget to mark strings as unicode strings (:samp:`'öäüß'`) when they contain non-ASCII content for proper encoding, and add a `# encoding: utf-8` to the top of all your .py files.

		Tip: You can find Glyphs’ localized languages here :samp:`Glyphs.defaults["AppleLanguages"]`.

		.. code-block:: python
			print(Glyphs.localize({
			    'en': 'Hello World',
			    'de': 'Hallöle Welt',
			    'fr': 'Bonjour tout le monde',
			    'es': 'Hola Mundo',
			}))

			# Given that your Mac’s system language is set to German
			# and Glyphs.app UI is set to use localization (change in app settings),
			# it will print:
			>> Hallöle Welt
