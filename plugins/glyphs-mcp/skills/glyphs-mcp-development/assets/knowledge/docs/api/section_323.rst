:mod:`GSLayer`
===============================================================================

Implementation of the layer object.

For details on how to access these layers, please see :attr:`GSGlyph.layers`

.. class:: GSLayer()

	Properties

		* :attr:`parent`
		* :attr:`name`
		* :attr:`master`
		* :attr:`associatedMasterId`
		* :attr:`layerId`
		* :attr:`attributes`
		* :attr:`color`
		* :attr:`colorObject`
		* :attr:`shapes`
		* :attr:`guides`
		* :attr:`annotations`
		* :attr:`hints`
		* :attr:`anchors`
		* :attr:`components`
		* :attr:`paths`
		* :attr:`selection`
		* :attr:`LSB`
		* :attr:`RSB`
		* :attr:`TSB`
		* :attr:`BSB`
		* :attr:`width`
		* :attr:`vertWidth`
		* :attr:`leftMetricsKey`
		* :attr:`rightMetricsKey`
		* :attr:`widthMetricsKey`
		* :attr:`topMetricsKey`
		* :attr:`bottomMetricsKey`
		* :attr:`bounds`
		* :attr:`selectionBounds`
		* :attr:`background`
		* :attr:`backgroundImage`
		* :attr:`bezierPath`
		* :attr:`openBezierPath`
		* :attr:`userData`
		* :attr:`smartComponentPoleMapping`
		* :attr:`isSpecialLayer`
		* :attr:`isMasterLayer`
		* :attr:`isBraceLayer`
		* :attr:`isBracketLayer`
		* :attr:`italicAngle`
		* :attr:`visible`

	Functions

		* :meth:`addMissingAnchors`
		* :meth:`addNodesAtExtremes`
		* :meth:`applyTransform`
		* :meth:`beginChanges`
		* :meth:`clear`
		* :meth:`clearSelection`
		* :meth:`compareString`
		* :meth:`connectAllOpenPaths`
		* :meth:`copy`
		* :meth:`copyDecomposedLayer`
		* :meth:`correctPathDirection`
		* :meth:`cutBetweenPoints`
		* :meth:`decomposeComponents`
		* :meth:`decomposeCorners`
		* :meth:`endChanges`
		* :meth:`intersections`
		* :meth:`intersectionsBetweenPoints`
		* :meth:`reinterpolate`
		* :meth:`removeOverlap`
		* :meth:`roundCoordinates`
		* :meth:`swapForegroundWithBackground`
		* :meth:`syncMetrics`
		* :meth:`transform`

	**Properties**
