.. attribute:: viewPort
		The visible area of the Edit view in screen pixel coordinates (view coordinates).

		The NSRect’s origin value describes the top-left corner (top-right for RTL, both at ascender height) of the combined glyphs’ bounding box (see :attr:`bounds <GSEditViewController.bounds>`), which also serves as the origin of the view plane.

		The NSRect’s size value describes the width and height of the visible area.

		When using drawing methods such as the view-coordinate-relative method in the Reporter Plugin, use these coordinates.

		:type: NSRect

		.. code-block:: python
			# The far corners of the Edit view:

			# Lower left corner of the screen
			x = font.currentTab.viewPort.origin.x
			y = font.currentTab.viewPort.origin.y

			# Top left corner of the screen
			x = font.currentTab.viewPort.origin.x
			y = font.currentTab.viewPort.origin.y + font.currentTab.viewPort.size.height

			# Top right corner of the screen
			x = font.currentTab.viewPort.origin.x + font.currentTab.viewPort.size.width
			y = font.currentTab.viewPort.origin.y + font.currentTab.viewPort.size.height

			# Bottom right corner of the screen
			x = font.currentTab.viewPort.origin.x + font.currentTab.viewPort.size.width
			y = font.currentTab.viewPort.origin.y
