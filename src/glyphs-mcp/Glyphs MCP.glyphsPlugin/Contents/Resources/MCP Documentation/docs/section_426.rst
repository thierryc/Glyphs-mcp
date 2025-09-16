.. attribute:: nextNode
		Returns the next node in the path.

		Please note that this is regardless of the position of the node in the path and will jump across the path border to the beginning of the path if the current node is the last.

		If you need to take into consideration the position of the node in the path, use the node’s index attribute and check it against the path length.

		:type: GSNode

		.. code-block:: python
			print(layer.paths[0].nodes[0].nextNode # returns the second node in the path (index 0 + 1))
			print(layer.paths[0].nodes[-1].nextNode # returns the first node in the path (last node >> jumps to beginning of path))

			# check if node is last node in path (with at least two nodes)
			print(layer.paths[0].nodes[0].index == (len(layer.paths[0].nodes) - 1)) # returns False for first node
			print(layer.paths[0].nodes[-1].index == (len(layer.paths[0].nodes) - 1)) # returns True for last node
