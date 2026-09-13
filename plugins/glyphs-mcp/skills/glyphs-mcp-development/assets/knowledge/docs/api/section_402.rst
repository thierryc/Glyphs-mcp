.. attribute:: componentLayer
		The :class:`GSLayer` the component is pointing to. This is read-only. In order to change the referenced base glyph, set :attr:`componentName <GSComponent.componentName>` to the new glyph name.

		For Smart Components, the `componentLayer` contains the interpolated result.

		:type: :class:`GSLayer`

		.. versionadded:: 2.5
