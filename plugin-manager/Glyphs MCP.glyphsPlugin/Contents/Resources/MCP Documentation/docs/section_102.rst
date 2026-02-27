.. attribute:: tabs
		List of open Edit view tabs in UI, as list of :class:`GSEditViewController` objects.

		:type: list

		.. code-block:: python
			# open new tab with text
			font.newTab('hello')

			# access all tabs
			for tab in font.tabs:
			    print(tab)

			# close last tab
			font.tabs[-1].close()
