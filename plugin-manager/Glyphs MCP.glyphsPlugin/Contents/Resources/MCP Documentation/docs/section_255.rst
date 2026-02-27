:mod:`GSGlyph`
===============================================================================

Implementation of the glyph object.

For details on how to access these glyphs, please see :class:`GSFont.glyphs`

.. class:: GSGlyph([name, autoName=True])

	:param name: The glyph name
	:param autoName: if the name should be converted to nice name

	Properties

	.. autosummary::

		case
		storeCase
		category
		storeCategory
		color
		colorObject
		direction
		storeDirection
		export
		font
		glyphInfo
		id
		layers
		locked
		name
		note
		parent
		productionName
		storeProductionName
		script
		storeScript
		smartComponentAxes
		sortName
		storeSortName
		sortNameKeep
		subCategory
		storeSubCategory
		tags
		unicode
		userData

		leftKerningGroup
		rightKerningGroup
		leftKerningKey
		topKerningGroup
		bottomKerningKey
		rightKerningKey
		topKerningKey
		bottomKerningKey
		leftMetricsKey
		rightMetricsKey
		widthMetricsKey

		string
		selected
		mastersCompatible
		lastChange

	Functions

	.. autosummary::

		beginUndo()
		copy()
		duplicate()
		endUndo()
		updateGlyphInfo()

	**Properties**
