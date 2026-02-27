.. attribute:: featurePrefixes
		Collection of :class:`GSFeaturePrefix` objects, containing stuff that needs to be outside of the OpenType features.

		:type: list

		.. code-block:: python
			# add a prefix
			font.featurePrefixes.append(GSFeaturePrefix('LanguageSystems', 'languagesystem DFLT dflt;'))

			# access all prefixes
			for prefix in font.featurePrefixes:
			    print(prefix.code)

			# access one prefix
			print(font.featurePrefixes['LanguageSystems'].code)

			# delete
			del font.featurePrefixes['LanguageSystems']
