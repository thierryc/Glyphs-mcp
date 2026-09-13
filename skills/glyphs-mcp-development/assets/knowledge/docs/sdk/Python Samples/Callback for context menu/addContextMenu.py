# MenuTitle: Add Context Menu Callback
# -*- coding: utf-8 -*-

__doc__ = """

"""

from GlyphsApp import GSCallbackHandler
from Cocoa import NSObject, NSMenuItem


class ContextMenuCallback (NSObject):
	def init(self):
		print("__init")
		GSCallbackHandler.addCallback_forOperation_(self, "GSContextMenuCallbackName")

	def contextMenuCallback_forSelectedLayers_event_(self, menu, layers, event):
		print("__menu", menu)
		# do something with the menu. e.g. add an menu item
		newMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Copy Production Name", self.menuAction_, "")
		newMenuItem.setRepresentedObject_(layers)
		newMenuItem.setTarget_(self)
		menu.addItem_(newMenuItem)

	def callOrder(self):
		return 1000000  # this makes sure to be called last

	def menuAction_(self, sender):
		print("__sender", sender, sender.representedObject())


contextMenuAdder = ContextMenuCallback.new()
