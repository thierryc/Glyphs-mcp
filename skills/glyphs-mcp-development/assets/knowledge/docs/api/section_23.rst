.. attribute:: handleSize
		Size of Bezier handles in Glyph Edit view. Possible value are 0–2. Corresponds to the ‘Handle size’ setting from the Preferences.

		To use the handle size for drawing in reporter plugins, you need to convert the handle size to a point size, and divide by the view’s scale factor. See example below.

		:type: int

		.. code-block:: python
			# Calculate handle size
			handSizeInPoints = 5 + Glyphs.handleSize * 2.5 # (= 5.0 or 7.5 or 10.0)
			scaleCorrectedHandleSize = handSizeInPoints / Glyphs.font.currentTab.scale

			# Draw point in size of handles
			point = NSPoint(100, 100)
			NSColor.redColor.set()
			rect = NSRect((point.x - scaleCorrectedHandleSize * 0.5, point.y - scaleCorrectedHandleSize * 0.5), (scaleCorrectedHandleSize, scaleCorrectedHandleSize))
			bezierPath = NSBezierPath.bezierPathWithOvalInRect_(rect)
			bezierPath.fill()
