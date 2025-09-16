.. attribute:: selection
		List of all selected objects in the glyph.

		This list contains **all selected items**, including **nodes**, **anchors**, **guides** etc.
		If you want to work specifically with nodes, for instance, you may want to cycle through the nodes (or anchors etc.) and check whether they are selected. See example below.

		:type: list

		.. code-block:: python
			# access all selected nodes
			for path in layer.paths:
			    for node in path.nodes: # (or path.anchors etc.)
			        print(node.selected)

			# clear selection
			layer.clearSelection()
