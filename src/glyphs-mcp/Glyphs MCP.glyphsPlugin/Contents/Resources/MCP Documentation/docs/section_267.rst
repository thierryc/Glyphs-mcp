:mod:`GSGlyph`
===============================================================================

Implementation of the glyph object.

For details on how to access these glyphs, please see :class:`GSFont.glyphs`

.. class:: GSGlyph([name, autoName=True])

	:param name: The glyph name
	:param autoName: if the name should be converted to nice name

	Properties

		* :attr:`parent`
		* :attr:`layers`
		* :attr:`name`
		* :attr:`unicode`
		* :attr:`unicodes`
		* :attr:`string`
		* :attr:`id`
		* :attr:`category`
		* :attr:`storeCategory`
		* :attr:`subCategory`
		* :attr:`storeSubCategory`
		* :attr:`group`
		* :attr:`groupIdx`
		* :attr:`storeGroup`
		* :attr:`case`
		* :attr:`storeCase`
		* :attr:`script`
		* :attr:`storeScript`
		* :attr:`productionName`
		* :attr:`storeProductionName`
		* :attr:`sortName`
		* :attr:`sortNameKeep`
		* :attr:`storeSortName`
		* :attr:`glyphInfo`
		* :attr:`leftKerningGroup`
		* :attr:`rightKerningGroup`
		* :attr:`leftKerningKey`
		* :attr:`topKerningGroup`
		* :attr:`bottomKerningKey`
		* :attr:`rightKerningKey`
		* :attr:`topKerningKey`
		* :attr:`leftMetricsKey`
		* :attr:`rightMetricsKey`
		* :attr:`widthMetricsKey`
		* :attr:`topMetricsKey`
		* :attr:`bottomMetricsKey`
		* :attr:`export`
		* :attr:`color`
		* :attr:`colorObject`
		* :attr:`note`
		* :attr:`selected`
		* :attr:`mastersCompatible`
		* :attr:`userData`
		* :attr:`smartComponentAxes`
		* :attr:`tags`
		* :attr:`lastChange`

	Functions

		* :meth:`beginUndo`
		* :meth:`copy`
		* :meth:`duplicate`
		* :meth:`endUndo`
		* :meth:`updateGlyphInfo`

	**Properties**
