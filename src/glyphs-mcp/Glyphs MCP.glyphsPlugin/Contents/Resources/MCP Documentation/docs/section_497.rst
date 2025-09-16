.. attribute:: scale
		Scale (zoom factor) of the Edit view. Useful for drawing activity in plugins.

		The scale changes with every zoom step of the Edit view. So if you want to draw objects (e.g. text, stroke thickness etc.) into the Edit view at a constant size relative to the UI (e.g. constant text size on screen), you need to calculate the object’s size relative to the scale factor. See example below.

		:type: float

		.. code-block:: python
			print(font.currentTab.scale)
			>> 0.414628537193

			# Calculate text size
			desiredTextSizeOnScreen = 10 #pt
			scaleCorrectedTextSize = desiredTextSizeOnScreen / font.currentTab.scale

			print(scaleCorrectedTextSize)
			>> 24.1179733255
