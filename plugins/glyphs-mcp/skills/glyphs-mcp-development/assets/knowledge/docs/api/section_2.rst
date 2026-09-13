:mod:`GSApplication`
===============================================================================

The mothership. Everything starts here.

.. code-block:: python
	print(Glyphs)

.. code-block:: python
	<Glyphs.app>

.. class:: GSApplication()

	Properties
		* :attr:`currentDocument`
		* :attr:`documents`
		* :attr:`font`
		* :attr:`fonts`
		* :attr:`reporters`
		* :attr:`activeReporters`
		* :attr:`filters`
		* :attr:`defaults`
		* :attr:`scriptAbbreviations`
		* :attr:`scriptSuffixes`
		* :attr:`languageScripts`
		* :attr:`languageData`
		* :attr:`unicodeRanges`
		* :attr:`editViewWidth`
		* :attr:`handleSize`
		* :attr:`versionString`
		* :attr:`versionNumber`
		* :attr:`buildNumber`
		* :attr:`menu`

	Functions

		* :meth:`open`
		* :meth:`showMacroWindow`
		* :meth:`clearLog`
		* :meth:`showGlyphInfoPanelWithSearchString`
		* :meth:`glyphInfoForName()`
		* :meth:`glyphInfoForUnicode()`
		* :meth:`niceGlyphName()`
		* :meth:`productionGlyphName()`
		* :meth:`ligatureComponents()`
		* :meth:`addCallback()`
		* :meth:`removeCallback()`
		* :meth:`redraw()`
		* :meth:`showNotification()`
		* :meth:`localize()`
		* :meth:`activateReporter()`
		* :meth:`deactivateReporter()`


	**Properties**
