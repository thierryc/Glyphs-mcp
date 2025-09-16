:mod:`GSComponent`
===============================================================================

Implementation of the component object.
For details on how to access them, please see :attr:`GSLayer.components`

.. class:: GSComponent(glyph [, position])

	:param glyph: a :class:`GSGlyph` object or the glyph name
	:param position: the position of the component as NSPoint

	Properties

	.. autosummary::

		position
		scale
		rotation
		slant
		componentName
		componentMasterId
		component
		layer
		transform
		bounds
		automaticAlignment
		anchor
		selected
		smartComponentValues
		bezierPath
		userData

	Functions

	.. autosummary::

		applyTransform()
		copy()
		decompose()

	**Properties**
