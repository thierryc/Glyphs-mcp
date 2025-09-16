Constants
=========

Node Types
==============

.. data:: LINE

	Line node.

.. data:: CURVE

	Curve node. Make sure that each curve node is preceded by two off-curve nodes.

.. data:: QCURVE

	Quadratic curve node. Make sure that each curve node is preceded by at least one off-curve node.

.. data:: OFFCURVE

	Off-curve node

Path attributes
==============

.. data:: FILL

	fill

.. data:: FILLCOLOR

	fillColor

.. data:: FILLPATTERNANGLE

	fillPatternAngle

.. data:: FILLPATTERNBLENDMODE

	fillPatternBlendMode

.. data:: FILLPATTERNFILE

	fillPatternFile

.. data:: FILLPATTERNOFFSET

	fillPatternOffset

.. data:: FILLPATTERNSCALE

	fillPatternScale

.. data:: STROKECOLOR

	strokeColor

.. data:: STROKELINECAPEND

	lineCapEnd

.. data:: STROKELINECAPSTART

	lineCapStart

.. data:: STROKELINEJOIN

	lineJoin

.. data:: STROKEPOSITION

	strokePos

.. data:: STROKEWIDTH

	strokeWidth

.. data:: STROKEHEIGHT

	strokeHeight

.. data:: GRADIENT

	gradient

.. data:: SHADOW

	shadow

.. data:: INNERSHADOW

	shadowIn

.. data:: MASK

	mask

File Format Versions
====================

A constant that is used when saving are reading .glyphs file but also for the clipboard.

.. data:: GSFormatVersion1

	The Format used by Glyphs 2

.. data:: GSFormatVersion3

	The Format used by Glyphs 3

.. data:: GSFormatVersionCurrent

	This will always return the format of the current app.


Export formats
==============

.. data:: OTF

	Write CFF based font

.. data:: TTF

	Write CFF based font

.. data:: VARIABLE

	Write Variable font

.. data:: UFO

	Write UFO based font

.. data:: WOFF

	Write WOFF

.. data:: WOFF2

	Write WOFF

.. data:: PLAIN

	do not package as webfont

.. versionadded:: 2.5


Info Property Keys
==================

.. data:: GSPropertyNameFamilyNamesKey

	Family Names

.. data:: GSPropertyNameDesignersKey

	Designers

.. data:: GSPropertyNameDesignerURLKey

	Designer URL

.. data:: GSPropertyNameManufacturersKey

	Manufacturers

.. data:: GSPropertyNameManufacturerURLKey

	Manufacturer URL

.. data:: GSPropertyNameCopyrightsKey

	Copyrights

.. data:: GSPropertyNameVersionStringKey

	Version String

.. data:: GSPropertyNameVendorIDKey

	VendorID

.. data:: GSPropertyNameUniqueIDKey

	UniqueID

.. data:: GSPropertyNameLicensesKey

	Licenses

.. data:: GSPropertyNameLicenseURLKey

	License URL

.. data:: GSPropertyNameTrademarksKey

	Trademarks

.. data:: GSPropertyNameDescriptionsKey

	Descriptions

.. data:: GSPropertyNameSampleTextsKey

	SampleTexts

.. data:: GSPropertyNamePostscriptFullNamesKey

	PostscriptFullNames

.. data:: GSPropertyNamePostscriptFontNameKey

	PostscriptFontName

.. data:: GSPropertyNameCompatibleFullNamesKey

	CompatibleFullNames

.. data:: GSPropertyNameStyleNamesKey

	StyleNames

.. data:: GSPropertyNameStyleMapFamilyNamesKey

	StyleMapFamilyNames

.. data:: GSPropertyNameStyleMapStyleNamesKey

	StyleMapStyleNames

.. data:: GSPropertyNamePreferredFamilyNamesKey

	PreferredFamilyNames

.. data:: GSPropertyNamePreferredSubfamilyNamesKey

	PreferredSubfamilyNames

.. data:: GSPropertyNameVariableStyleNamesKey

	VariableStyleNames

.. data:: GSPropertyNameWWSFamilyNameKey

	WWSFamilyName

.. data:: GSPropertyNameWWSSubfamilyNameKey

	WWSSubfamilyName

.. data:: GSPropertyNameVariationsPostScriptNamePrefixKey

	VariationsPostScriptNamePrefix

.. versionadded:: 3.1

Instance Types
==============

.. data:: INSTANCETYPESINGLE

	single interpolation instance

.. data:: INSTANCETYPEVARIABLE

	variable font setting

.. versionadded:: 3.0.1

Hint Types
==========

.. data:: TOPGHOST

	Top ghost for PS hints

.. data:: STEM

	Stem for PS hints

.. data:: BOTTOMGHOST

	Bottom ghost for PS hints

.. data:: TTSNAP

	Snap for TT hints

.. data:: TTSTEM

	Stem for TT hints

.. data:: TTSHIFT

	Shift for TT hints

.. data:: TTINTERPOLATE

	Interpolation for TT hints

.. data:: TTDIAGONAL

	Diagonal for TT hints

.. data:: TTDELTA

	Delta TT hints

.. data:: CORNER

	Corner Component

	.. code-block:: python
		path = Layer.shapes[0]
		brush = GSHint()
		brush.name = "_corner.test"
		brush.type = CORNER
		brush.originNode = path.nodes[1]
		Layer.hints.append(brush)

.. data:: CAP

	Cap Component

.. data:: BRUSH

	Brush Component

	.. versionadded:: 3.1

.. data:: SEGMENT

	Segment Component

	.. versionadded:: 3.1


Hint Option
===========

This is only used for TrueType hints.

.. data:: TTROUND

	Round to grid

.. data:: TTROUNDUP

	Round up

.. data:: TTROUNDDOWN

	Round down

.. data:: TTDONTROUND

	Don’t round at all

.. data:: TRIPLE = 128

	Indicates a triple hint group. There need to be exactly three horizontal TTStem hints with this setting to take effect.

Menu Tags
=========

This are tags to access the menu items in the apps main menu. Please see :attr:`GSApplication.menu` for details

.. data:: APP_MENU

	The 'Glyphs' menu

.. data:: FILE_MENU

	The File menu

.. data:: EDIT_MENU

	The Edit menu

.. data:: GLYPH_MENU

	The Glyph menu

.. data:: PATH_MENU

	The Path menu

.. data:: FILTER_MENU

	The Filter menu

.. data:: VIEW_MENU

	The View menu

.. data:: SCRIPT_MENU

	The Script menu

.. data:: WINDOW_MENU

	The Window menu

.. data:: HELP_MENU

	The Help menu

Menu States
===========

.. data:: ONSTATE

	The menu entry will have a checkbox

.. data:: OFFSTATE

	The menu entry will have no checkbox

.. data:: MIXEDSTATE

	The menu entry will have horizontal line

Callback Keys
=============

This are the available callbacks

.. data:: DRAWFOREGROUND

	to draw in the foreground

.. data:: DRAWBACKGROUND

	to draw in the background

.. data:: DRAWINACTIVE

	draw inactive glyphs

.. data:: DOCUMENTOPENED

	is called if a new document is opened

.. data:: DOCUMENTACTIVATED

	is called when the document becomes the active document

.. data:: DOCUMENTWASSAVED

	is called when the document is saved.
	The document itself is passed in notification.object()

.. data:: DOCUMENTEXPORTED

	if a font is exported. This is called for every instance and ``notification.object()`` will contain the path to the final font file.

	.. code-block:: python
		def exportCallback(info):
		    try:
		        print(info.object())
		    except:
		        # Error. Print exception.
		        import traceback
		        print(traceback.format_exc())

		# add your function to the hook
		Glyphs.addCallback(exportCallback, DOCUMENTEXPORTED)

.. data:: DOCUMENTCLOSED

	is called when the document is closed

	.. deprecated:: 3.0.4
		please use DOCUMENTWILLCLOSE

.. data:: DOCUMENTWILLCLOSE

	is called just before a document will be closed

	the info object contains the GSWindowController object

	.. versionadded:: 3.0.4

.. data:: DOCUMENTDIDCLOSE

	is called after a document was closed

	the info object contains the NSDocument object

	.. versionadded:: 3.0.4

.. data:: TABDIDOPEN

	if a new tab is opened

.. data:: TABWILLCLOSE

	if a tab is closed

.. data:: UPDATEINTERFACE

	if some thing changed in the edit view. Maybe the selection or the glyph data.

.. data:: MOUSEMOVED

	is called if the mouse is moved. If you need to draw something, you need to call :meth:`Glyphs.redraw() <GSApplication.redraw()>` and also register to one of the drawing callbacks.

.. data:: FILTER_FLAT_KERNING

	is called when exporting a kern table

	In a (general) plugin, implement a method like this:

	.. code-block:: python
		@objc.typedSelector(b'@@:@o^@')
		def filterFlatKerning_error_(self, flatKerning, error):
			newKerning = list()
			for kern in flatKerning:
				name1 = kern[0]
				name2 = kern[1]
				if len(name1) > 1 and len(name2) > 1: # this is way oversimplified.
					continue
				if abs(kern[2]) < 10: # ignore small pairs
					continue
				newKerning.append(kern)
			return newKerning, None

	Register the callback like this:

	.. code-block:: python
		GSCallbackHandler.addCallback_forOperation_(self, FILTER_FLAT_KERNING) # self needs to be a subclass of NSObject (as all plugins are)

	.. versionadded:: 3.2

Writing Directions
==================

The writing directions of the Edit View.

.. data:: GSBIDI

	for characters that follow the main writing direction (like punctuation)

.. data:: GSLTR

	Left to Right (e.g. Latin)

.. data:: GSRTL

	Right to Left (e.g. Arabic, Hebrew)

.. data:: GSVertical

	Top to Bottom, Right to Left (e.g. Chinese, Japanese, Korean)

.. data:: GSVerticalToRight

	Top to Bottom, Left to Right (e.g. Mongolian)

Shape Type
==========

.. data:: GSShapeTypePath

	Path

.. data:: GSShapeTypeComponent

	Component

Annotation types
================

.. data:: TEXT

.. data:: ARROW

.. data:: CIRCLE

.. data:: PLUS

.. data:: MINUS

Inspector Sizes
===============

.. data:: GSInspectorSizeSmall

.. data:: GSInspectorSizeRegular

.. data:: GSInspectorSizeLarge

.. data:: GSInspectorSizeXLarge

Metrics Types
=============

metrics types are used in :attr:`GSFont.metrics`. see :attr:`GSMetric.type`

.. data:: GSMetricsTypeUndefined

.. data:: GSMetricsTypeAscender

.. data:: GSMetricsTypeCapHeight

.. data:: GSMetricsTypeSlantHeight

.. data:: GSMetricsTypexHeight

.. data:: GSMetricsTypeMidHeight

.. data:: GSMetricsTypeBodyHeight

.. data:: GSMetricsTypeDescender

.. data:: GSMetricsTypeBaseline

.. data:: GSMetricsTypeItalicAngle
