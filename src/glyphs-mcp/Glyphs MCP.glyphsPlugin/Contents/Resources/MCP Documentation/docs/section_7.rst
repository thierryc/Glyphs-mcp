.. attribute:: reporters
		List of available reporter plug-ins (same as bottom section in the 'View' menu). These are the actual objects. You can get hold of their names using `object.__class__.__name__`.

		Also see :meth:`GSApplication.activateReporter()` and :meth:`GSApplication.deactivateReporter()` methods below to activate/deactivate them.

		:type: list

		.. code-block:: python
			# List of all reporter plug-ins
			print(Glyphs.reporters)

			# Individual plug-in class names
			for reporter in Glyphs.reporters:
			    print(reporter.__class__.__name__)

			# Activate a plugin
			Glyphs.activateReporter(Glyphs.reporters[0]) # by object
			Glyphs.activateReporter('GlyphsMasterCompatibility') # by class name
