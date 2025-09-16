.. attribute:: features
		Collection of :class:`GSFeature` objects, representing OpenType features.

		:type: list

		.. code-block:: python
			# add a feature
			font.features.append(GSFeature('liga', 'sub f i by fi;'))

			# access all features
			for feature in font.features:
			    print(feature.code)

			# access one feature
			print(font.features['liga'].code)

			# delete a feature
			del font.features['liga']
