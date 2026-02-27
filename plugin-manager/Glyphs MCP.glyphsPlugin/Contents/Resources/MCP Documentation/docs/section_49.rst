.. attribute:: stems
		The stems. A list of :class:`GSMetric` objects. For each metric, there is a metricsValue in the masters, linked by the `id`.

		:type: list, dict

		.. code-block:: python
			font.stems[0].horizontal = False

			# add a stem
			stem = GSMetric()
			stem.horizontal = False # or True
			stem.name = "Some Name"
			font.stems.append(stem)
			master.stems[stem.name] = 123
