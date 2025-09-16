.. attribute:: menu
		Add menu items to Glyphs’ main menus.

		Following constants for accessing the menus are defined:
		:const:`APP_MENU`, :const:`FILE_MENU`, :const:`EDIT_MENU`, :const:`GLYPH_MENU`, :const:`PATH_MENU`, :const:`FILTER_MENU`, :const:`VIEW_MENU`, :const:`SCRIPT_MENU`, :const:`WINDOW_MENU`, :const:`HELP_MENU`

		.. code-block:: python
			def doStuff_(self, sender):
			    # do stuff
			
			newMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(self.name, self.doStuff_, "")
			newMenuItem.setTarget_(self)
			Glyphs.menu[EDIT_MENU].append(newMenuItem)
