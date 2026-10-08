.. function:: addCallback(function, hook)

		Add a user-defined function to the glyph window’s drawing operations, in the foreground and background for the active glyph as well as in the inactive glyphs.

		The function names are used to add/remove the functions to the hooks, so make sure to use unique function names.

		Your function needs to accept two values: `layer` which will contain the respective :class:`GSLayer` object of the layer we’re dealing with and `info` which is a dictionary and contains the value `Scale` (for the moment).

		For the defined keys see `Callback Keys`_

		.. code-block:: python
			def drawGlyphIntoBackground(layer, info):

			    # Due to internal Glyphs.app structure, we need to catch and print exceptions
			    # of these callback functions with try/except like so:
			    try:
			        # Your drawing code here
			        NSColor.redColor().set()
			        layer.bezierPath.fill()
			    # Error. Print exception.
			    except:
			        import traceback
			        print(traceback.format_exc())

			# add your function to the hook
			Glyphs.addCallback(drawGlyphIntoBackground, DRAWBACKGROUND)
