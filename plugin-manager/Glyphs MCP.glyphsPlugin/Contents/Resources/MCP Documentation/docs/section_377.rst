.. function:: transform(transform, [selection=False, components=True])

		Apply a :attr:`NSAffineTransform` to the layer.

		:param transform: A :attr:`NSAffineTransform`
		:param selection: check selection
		:param components: if components should be transformed

		.. code-block:: python
			transformation = NSAffineTransform()
			transformation.rotate(45, (200, 200))
			layer.transform(transformation)
