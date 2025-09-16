.. attribute:: annotations
		List of :class:`GSAnnotation` objects.

		:type: list

		.. code-block:: python
			# access all annotations
			for annotation in layer.annotations:
			    print(annotation)

			# add new annotation
			newAnnotation = GSAnnotation()
			newAnnotation.type = TEXT
			newAnnotation.text = 'Fuck, this curve is ugly!'
			layer.annotations.append(newAnnotation)

			# delete annotation
			del layer.annotations[0]

			# copy annotations from another layer
			import copy
			layer.annotations = copy.copy(anotherlayer.annotations)
