# MenuTitle: Document Exported Callback
# -*- coding: utf-8 -*-

__doc__ = """"""

from GlyphsApp import Glyphs, DOCUMENTEXPORTED


def exportCallback(info):
	try:
		print(info.object())
	except:
		# Error. Print exception.
		import traceback
		print(traceback.format_exc())


# add your function to the hook
Glyphs.addCallback(exportCallback, DOCUMENTEXPORTED)
