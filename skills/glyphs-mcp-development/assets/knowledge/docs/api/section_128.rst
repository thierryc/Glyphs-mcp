.. function:: newTab([tabText])

		Opens a new tab in the current document window, optionally with text, and return that tab object

		:param tabText: Text or glyph names escaped with '/' OR list of layers

		.. code-block:: python
			# open new tab
			tab = font.newTab('abcdef')
			print(tab)

			# or
			tab = font.newTab([layer1, layer2])
			print(tab)
