:mod:`GSNode`
===============================================================================

Implementation of the node object.

For details on how to access them, please see :attr:`GSPath.nodes`

.. class:: GSNode([pt, type = type])

	:param pt: The position of the node.
	:param type: The type of the node, LINE, CURVE or OFFCURVE

	Properties

		* :attr:`position`
		* :attr:`type`
		* :attr:`connection`
		* :attr:`selected`
		* :attr:`index`
		* :attr:`nextNode`
		* :attr:`prevNode`
		* :attr:`name`
		* :attr:`orientation`

	Functions

		* :meth:`copy`
		* :meth:`makeNodeFirst`
		* :meth:`toggleConnection`

	**Properties**
