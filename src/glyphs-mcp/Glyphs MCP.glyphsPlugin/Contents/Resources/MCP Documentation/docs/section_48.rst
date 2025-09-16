.. attribute:: metrics
		a list of all :class:`GSMetric` objects.

		:type: list

		.. code-block:: python
			# to add a new metric
			metric = GSMetric(GSMetricsTypexHeight)
			font.metrics.append(metric)
			metricValue = master.metricValues[metric.id]
			metricValue.position = 543
			metricValue.overshoot = 17
