.. attribute:: nameParticles

		The name particles, keyed by :attr:`GSAxis.axisId` and ordered like :attr:`GSFont.axes`.
		Each value is a list of :class:`GSNameParticle` objects. Can also be accessed by
		axis index.

		Use :meth:`addNameParticle()` and :meth:`removeNameParticle()` to add and remove
		single particles.

		:type: dict

		.. versionadded:: 4
