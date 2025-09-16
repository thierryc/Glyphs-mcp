:mod:`GSLayer`
===============================================================================

Implementation of the layer object.

For details on how to access these layers, please see :attr:`GSGlyph.layers`

.. class:: GSLayer()

	Properties

	.. autosummary::

		parent
		name
		master
		associatedMasterId
		layerId
		attributes
		color
		colorObject
		shapes
		guides
		annotations
		hints
		anchors
		components
		paths
		selection
		LSB
		RSB
		TSB
		BSB
		width
		vertWidth
		leftMetricsKey
		rightMetricsKey
		widthMetricsKey
		bounds
		selectionBounds
		background
		backgroundImage
		bezierPath
		openBezierPath
		userData
		smartComponentPoleMapping
		isSpecialLayer
		isMasterLayer
		italicAngle
		visible

	Functions

	.. autosummary::

		addMissingAnchors()
		addNodesAtExtremes()
		applyTransform()
		beginChanges()
		clear()
		clearSelection()
		compareString()
		connectAllOpenPaths()
		copy()
		copyDecomposedLayer()
		correctPathDirection()
		cutBetweenPoints()
		decomposeComponents()
		decomposeCorners()
		endChanges()
		intersections()
		intersectionsBetweenPoints()
		reinterpolate()
		removeOverlap()
		roundCoordinates()
		swapForegroundWithBackground()
		syncMetrics()
		transform()

	**Properties**
