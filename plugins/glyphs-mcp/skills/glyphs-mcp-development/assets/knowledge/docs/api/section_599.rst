.. function:: divideCurve(P0, P1, P2, P3, t)

	Divides the curve using the De Casteljau’s algorithm.

	:param P0: The start point of the curve (NSPoint)
	:param P1: The first off curve point
	:param P2: The second off curve point
	:param P3: The end point of the curve
	:param t: The time parameter
	:return: A list of points that represent two curves. (Q0, Q1, Q2, Q3, R1, R2, R3). Note that the ‘middle’ point is only returned once.
	:rtype: list
