.. attribute:: classes
		Collection of :class:`GSClass` objects, representing OpenType glyph classes.

		:type: list

		.. code-block:: python
			# add a class
			font.classes.append(GSClass('uppercaseLetters', 'A B C D E'))

			# access all classes
			for class in font.classes:
			    print(class.name)

			# access one class
			print(font.classes['uppercaseLetters'].code)

			# delete a class
			del font.classes['uppercaseLetters']
