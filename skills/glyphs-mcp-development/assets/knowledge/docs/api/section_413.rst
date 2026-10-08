:mod:`GSComponent`
===============================================================================

Implementation of the component object.
For details on how to access them, please see :attr:`GSLayer.components`

.. class:: GSComponent(glyph [, position])

	:param glyph: a :class:`GSGlyph` object or the glyph name
	:param position: the position of the component as NSPoint

	Properties

		* :attr:`position`
		* :attr:`scale`
		* :attr:`rotation`
		* :attr:`slant`
		* :attr:`componentName`
		* :attr:`componentMasterId`
		* :attr:`component`
		* :attr:`alignment`
		* :attr:`layer`
		* :attr:`transform`
		* :attr:`bounds`
		* :attr:`automaticAlignment`
		* :attr:`anchor`
		* :attr:`selected`
		* :attr:`smartComponentValues`
		* :attr:`bezierPath`
		* :attr:`userData`
		* :attr:`traverseAnchors`

	Functions

		* :meth:`applyTransform`
		* :meth:`copy`
		* :meth:`decompose`

	**Properties**
