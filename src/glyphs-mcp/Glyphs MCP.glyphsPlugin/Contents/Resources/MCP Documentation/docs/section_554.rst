.. function:: open()
		opens the Preview Text Window

	.. code-block:: python
		# open PreviewTextWindow
		PreviewTextWindow.open()

		# setting instance in PreviewTextWindow to "Regular"
		font = PreviewTextWindow.font
		instanceNames = [instance.name for instance in font.instances]
		regularIndex = instanceNames.index("Regular")
		PreviewTextWindow.instanceIndex = regularIndex

		# setting text and font size value
		PreviewTextWindow.text = 'hamburgefontsiv'
		PreviewTextWindow.fontSize = 200
