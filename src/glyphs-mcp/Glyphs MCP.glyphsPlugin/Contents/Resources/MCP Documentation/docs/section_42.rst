:mod:`GSFont`
===============================================================================

Implementation of the font object. This object is host to the :class:`masters <GSFontMaster>` used for interpolation. Even when no interpolation is involved, for the sake of object model consistency there will still be one master and one instance representing a single font.

Also, the :class:`glyphs <GSGlyph>` are attached to the Font object right here, not one level down to the masters. The different masters’ glyphs are available as :class:`layers <GSLayer>` attached to the glyph objects which are attached here.

.. class:: GSFont()

	Properties

	.. autosummary::

		axes
		classes
		customParameters
		date
		featurePrefixes
		features
		glyphs
		instances
		kerning
		kerningLTR
		kerningRTL
		kerningVertical
		masters
		note
		parent
		properties
		stems
		tempData
		upm
		userData

		compatibleFullName
		compatibleFullNames
		copyright
		copyrights
		description
		descriptions
		designer
		designers
		designerURL
		familyName
		familyNames
		license
		licenses
		manufacturer
		manufacturers
		manufacturerURL
		sampleText
		sampleTexts
		trademark
		trademarks
		versionMajor
		versionMinor

		disablesAutomaticAlignment
		disablesNiceNames
		grid
		gridLength
		gridSubDivision
		keyboardIncrement
		keyboardIncrementBig
		keyboardIncrementHuge
		previewRemoveOverlap
		snapToObjects

		currentTab
		currentText
		filepath
		fontView
		masterIndex
		selectedFontMaster
		selectedLayers
		selection
		tabs
		tool
		tools



	Functions

	.. autosummary::

		close()
		compileFeatures()
		copy()
		disableUpdateInterface()
		enableUpdateInterface()
		export()
		kerningForPair()
		newTab()
		removeKerningForPair()
		save()
		setKerningForPair()
		show()
		updateFeatures()


	**Properties**
