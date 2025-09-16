.. attribute:: interpolatedFont
		Returns a ready interpolated :class:`GSFont` object representing this instance. Other than the source object, this interpolated font will contain only one master and one instance.

		Note: When accessing several properties of such an instance consecutively, it is advisable to create the instance once into a variable and then use that. Otherwise, the instance object will be completely interpolated upon each access. See sample below.

		:type: :class:`GSFont`

		.. code-block:: python
			# create instance once
			interpolated = Glyphs.font.instances[0].interpolatedFont

			# then access it several times
			print(interpolated.masters)
			>> (<GSFontMaster "Light" width 100.0 weight 75.0>)
			print(interpolated.instances)
			>> (<GSInstance "Web" width 100.0 weight 75.0>)
