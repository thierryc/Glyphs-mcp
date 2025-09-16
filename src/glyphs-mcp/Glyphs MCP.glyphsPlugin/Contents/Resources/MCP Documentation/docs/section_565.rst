.. function:: insert(idx, item)

		:param idx: the index
		:param item: a NSMenuItem

		inserts the item into the items submenu at the specified index


:mod:`NSMenuItem`
===============================================================================

The NSMenuItem object.

.. class:: NSMenuItem

	:param title: The title of the item.
	:param callback: a method/selector that is called when the menu item is clicked.
	:param target: the object that the selector is called on.
	:param keyboard: A keyboard short key. e.g. "k"
	:param modifier: the modifiers (e.g. the Command key). Add all modifier of all keys you like together (e.g. NSCommandKeyMask + NSAlternateKeyMask)

	When called from a class that inherits from NSObject (e.g. plugins), use callback and target=self. Don’t add the ``@objc.python_method`` decorator.
	When called from a script, only set the callback with any python method

	Properties

	Functions
	.. autosummary::

		append()
		insert()
