.. attribute:: filters
		List of available filters (same as 'Filter' menu). These are the actual objects.

		Below sample code shows how to get hold of a particular filter and use it. You invoke it using the `processFont_withArguments_()` function for old plugins, or the `filter()` function for newer plugins.
		As arguments you use the list obtained by clicking on 'Copy Custom Parameter' button in the filter’s dialog (gear icon) and convert it to a list.
		In the `include` option you can supply a comma-separated list of glyph names.

		:type: list

		.. code-block:: python
			# Helper function to get filter by its class name
			def filterForName(name):
			    for filter in Glyphs.filters:
			        if filter.__class__.__name__ == name:
			            return filter

			# Get the filter
			offsetCurveFilter = filterForName('GlyphsFilterOffsetCurve')

			# Run the filter (old plugins)
			# The arguments came from the 'Copy Custom Parameter' as:
			# Filter = "GlyphsFilterOffsetCurve;10;10;1;0.5;"
			offsetCurveFilter.processFont_withArguments_(font, ['GlyphsFilterOffsetCurve', '10', '10', '1', '0.5', 'include:%s' % glyph.name])

			# If the plugin were a new filter, the same call would look like this:
			# (run on a specific layer, not the first layer glyphs in the include-list)
			# The arguments list is a dictionary with either incrementing integers as keys or names (as per 'Copy Custom Parameter' list)
			offsetCurveFilter.filter(layer, False, {0: 10, 1: 10, 2: 1, 3: 0.5})

		.. versionadded:: After 2.4.2
