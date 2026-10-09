:mod:`GSFeature`
===============================================================================

Implementation of the feature object. It is used to implement OpenType Features in the Font Info.

For details on how to access them, please look at :class:`GSFont.features`

.. class:: GSFeature([tag, code])

	:param tag: The feature name
	:param code: The feature code in Adobe FDK syntax

	Properties

		* :attr:`name`
		* :attr:`code`
		* :attr:`automatic`
		* :attr:`notes`
		* :attr:`active`
		* :attr:`layers`

	Functions

		* :meth:`update`

	**Properties**
