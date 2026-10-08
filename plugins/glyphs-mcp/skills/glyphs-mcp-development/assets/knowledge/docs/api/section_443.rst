:mod:`GSSmartComponentAxis`
===============================================================================

Implementation of the Smart Component interpolation axis object.
For details on how to access them, please see :attr:`GSGlyph.smartComponentAxes`

.. versionadded:: 2.3

.. deprecated:: 4
	Smart glyphs now use regular :class:`GSAxis` objects in :attr:`GSGlyph.axes` (exactly like :attr:`GSFont.axes`). Smart layers are positioned with :attr:`GSLayer.attributes` ["coordinates"], keyed by ``axis.axisId``.

.. class:: GSSmartComponentAxis()

	Properties

		* :attr:`name`
		* :attr:`topValue`
		* :attr:`bottomValue`

	**Properties**
