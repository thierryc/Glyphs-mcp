.. attribute:: metrics

		a dict of all :class:`GSMetricStore` objects. Keys are font.metrics[].id

		:type: dict

		.. code-block:: python
			for metric in Font.metrics:
			    if metric.type == GSMetricsTypexHeight and metric.filter is None:
			        metricValue = master.metrics[metric.id]
			        metricValue.position = 543
			        metricValue.overshoot = 17

		.. versionadded:: 3
