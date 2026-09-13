:mod:`GSFont`
===============================================================================

Implementation of the font object. This object is host to the :class:`masters <GSFontMaster>` used for interpolation. Even when no interpolation is involved, for the sake of object model consistency there will still be one master and one instance representing a single font.

Also, the :class:`glyphs <GSGlyph>` are attached to the Font object right here, not one level down to the masters. The different masters’ glyphs are available as :class:`layers <GSLayer>` attached to the glyph objects which are attached here.

.. class:: GSFont(([path]))

	:param path: the path to a glyphs file

	Properties

		* :attr:`parent`
		* :attr:`masters`
		* :attr:`axes`
		* :attr:`properties`
		* :attr:`stems`
		* :attr:`instances`
		* :attr:`glyphs`
		* :attr:`classes`
		* :attr:`features`
		* :attr:`featurePrefixes`
		* :attr:`copyright`
		* :attr:`copyrights`
		* :attr:`license`
		* :attr:`licenses`
		* :attr:`designer`
		* :attr:`designers`
		* :attr:`designerURL`
		* :attr:`manufacturer`
		* :attr:`manufacturers`
		* :attr:`manufacturerURL`
		* :attr:`familyNames`
		* :attr:`trademark`
		* :attr:`trademarks`
		* :attr:`sampleText`
		* :attr:`sampleTexts`
		* :attr:`description`
		* :attr:`descriptions`
		* :attr:`compatibleFullName`
		* :attr:`compatibleFullNames`
		* :attr:`versionMajor`
		* :attr:`versionMinor`
		* :attr:`date`
		* :attr:`familyName`
		* :attr:`upm`
		* :attr:`note`
		* :attr:`kerning`
		* :attr:`userData`
		* :attr:`grid`
		* :attr:`gridSubDivision`
		* :attr:`gridLength`
		* :attr:`keyboardIncrement`
		* :attr:`keyboardIncrementBig`
		* :attr:`keyboardIncrementHuge`
		* :attr:`snapToObjects`
		* :attr:`disablesNiceNames`
		* :attr:`customParameters`
		* :attr:`selection`
		* :attr:`selectedLayers`
		* :attr:`selectedFontMaster`
		* :attr:`masterIndex`
		* :attr:`currentText`
		* :attr:`tabs`
		* :attr:`fontView`
		* :attr:`currentTab`
		* :attr:`filepath`
		* :attr:`tool`
		* :attr:`tools`
		* :attr:`appVersion`

	Functions

		* :meth:`close`
		* :meth:`compileFeatures`
		* :meth:`copy`
		* :meth:`disableUpdateInterface`
		* :meth:`enableUpdateInterface`
		* :meth:`export`
		* :meth:`kerningForPair`
		* :meth:`newTab`
		* :meth:`removeKerningForPair`
		* :meth:`save`
		* :meth:`setKerningForPair`
		* :meth:`show`
		* :meth:`updateFeatures`


	**Properties**
