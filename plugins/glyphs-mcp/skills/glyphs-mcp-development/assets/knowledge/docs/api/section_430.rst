:mod:`GSPath`
===============================================================================

Implementation of the path object.

For details on how to access them, please see :attr:`GSLayer.paths`

If you build a path in code, make sure that the structure is valid. A curve node has to be preceded by two off-curve nodes. And an open path has to start with a line node.

.. class:: GSPath()

	Properties

		* :attr:`parent`
		* :attr:`nodes`
		* :attr:`segments`
		* :attr:`closed`
		* :attr:`direction`
		* :attr:`bounds`
		* :attr:`selected`
		* :attr:`bezierPath`
		* :attr:`attributes`
		* :attr:`tempData`

	Functions

		* :meth:`addNodesAtExtremes`
		* :meth:`applyTransform`
		* :meth:`copy`
		* :meth:`reverse`

	**Properties**
