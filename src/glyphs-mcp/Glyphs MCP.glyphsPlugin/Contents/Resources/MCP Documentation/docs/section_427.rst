.. attribute:: prevNode
		Returns the previous node in the path.

		Please note that this is regardless of the position of the node in the path, and will jump across the path border to the end of the path if the current node is the first.

		If you need to take into consideration the position of the node in the path, use the node’s index attribute and check it against the path length.

		:type: GSNode

		.. code-block:: python
			print(layer.paths[0].nodes[0].prevNode) # returns the last node in the path (first node >> jumps to end of path)
			print(layer.paths[0].nodes[-1].prevNode) # returns second last node in the path

			# check if node is first node in path (with at least two nodes)
			print(layer.paths[0].nodes[0].index == 0) # returns True for first node
			print(layer.paths[0].nodes[-1].index == 0) # returns False for last node
