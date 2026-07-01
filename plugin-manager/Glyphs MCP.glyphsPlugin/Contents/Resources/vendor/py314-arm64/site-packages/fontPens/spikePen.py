from math import atan2, cos, pi, sin

from fontTools.pens.basePen import BasePen

from fontPens.flattenPen import FlattenPen


class SpikePen(BasePen):
    """
    Add narly spikes or dents to the glyph.
    patternFunc is an optional function which recalculates the offset.
    """

    def __init__(self, otherPen, segmentLength=20, spikeLength=40, patternFunc=None):
        self.otherPen = otherPen
        self.segmentLength = segmentLength
        self.spikeLength = spikeLength
        self.patternFunc = patternFunc

    def _moveTo(self, pt):
        self._points = [pt]

    def _lineTo(self, pt):
        self._points.append(pt)

    def _processPoints(self):
        pointCount = len(self._points)
        for i in range(0, pointCount):
            x, y = self._points[i]

            if not i % 2:
                previousPoint = self._points[i - 1]
                nextPoint = self._points[(i + 1) % pointCount]
                angle = atan2(
                    previousPoint[0] - nextPoint[0], previousPoint[1] - nextPoint[1]
                )
                if self.patternFunc is not None:
                    thisSpikeLength = self.patternFunc(self.spikeLength)
                else:
                    thisSpikeLength = self.spikeLength
                x -= sin(angle + 0.5 * pi) * thisSpikeLength
                y -= cos(angle + 0.5 * pi) * thisSpikeLength

            if i == 0:
                self.otherPen.moveTo((x, y))
            else:
                self.otherPen.lineTo((x, y))

    def closePath(self):
        # pop last point
        self._points.pop()
        self._processPoints()
        self.otherPen.closePath()

    def endPath(self):
        self._processPoints()
        self.otherPen.endPath()


def spikeGlyph(aGlyph, segmentLength=20, spikeLength=40, patternFunc=None):
    from fontTools.pens.recordingPen import RecordingPen

    recorder = RecordingPen()
    spikePen = SpikePen(recorder, spikeLength=spikeLength, patternFunc=patternFunc)
    filterPen = FlattenPen(
        spikePen, approximateSegmentLength=segmentLength, segmentLines=True
    )
    aGlyph.draw(filterPen)
    aGlyph.clear()
    recorder.replay(aGlyph.getPen())
    return aGlyph


# =========
# = tests =
# =========


def _makeTestGlyphRect():
    # make a simple glyph that we can test the pens with.
    from fontParts.fontshell import RGlyph

    testGlyph = RGlyph()
    testGlyph.name = "testGlyph"
    testGlyph.width = 500
    pen = testGlyph.getPen()
    pen.moveTo((100, 100))
    pen.lineTo((100, 300))
    pen.lineTo((300, 300))
    pen.lineTo((300, 100))
    pen.closePath()
    return testGlyph


def _makeTestGlyphLine():
    from fontParts.fontshell import RGlyph

    testGlyph = RGlyph()
    testGlyph.name = "testGlyph"
    testGlyph.width = 500
    testPen = testGlyph.getPen()
    testPen.moveTo((10, 0))
    testPen.lineTo((30, 0))
    testPen.lineTo((50, 0))
    testPen.lineTo((70, 0))
    testPen.lineTo((90, 0))
    testPen.endPath()
    return testGlyph


def _testSpikePen():
    """
    >>> from fontPens.printPen import PrintPen
    >>> glyph = _makeTestGlyphLine()
    >>> pen = SpikePen(PrintPen())
    >>> glyph.draw(pen)
    pen.moveTo((9.999999999999995, 40.0))
    pen.lineTo((30, 0))
    pen.lineTo((50.0, -40.0))
    pen.lineTo((70, 0))
    pen.lineTo((90.0, 40.0))
    pen.endPath()
    """


def _testSpikeGlyph():
    """
    >>> from fontPens.printPen import PrintPen
    >>> glyph = _makeTestGlyphRect()
    >>> spikeGlyph(glyph) #doctest: +ELLIPSIS
    <RGlyph...
    >>> glyph.draw(PrintPen())
    pen.moveTo((128.2842712474619, 128.2842712474619))
    pen.lineTo((100.0, 120.0))
    pen.lineTo((140.0, 140.0))
    pen.lineTo((100.0, 160.0))
    pen.lineTo((140.0, 180.0))
    pen.lineTo((100.0, 200.0))
    pen.lineTo((140.0, 220.0))
    pen.lineTo((100.0, 240.0))
    pen.lineTo((140.0, 260.0))
    pen.lineTo((100.0, 280.0))
    pen.lineTo((128.2842712474619, 271.7157287525381))
    pen.lineTo((120.0, 300.0))
    pen.lineTo((140.0, 260.0))
    pen.lineTo((160.0, 300.0))
    pen.lineTo((180.0, 260.0))
    pen.lineTo((200.0, 300.0))
    pen.lineTo((220.0, 260.0))
    pen.lineTo((240.0, 300.0))
    pen.lineTo((260.0, 260.0))
    pen.lineTo((280.0, 300.0))
    pen.lineTo((271.7157287525381, 271.7157287525381))
    pen.lineTo((300.0, 280.0))
    pen.lineTo((260.0, 260.0))
    pen.lineTo((300.0, 240.0))
    pen.lineTo((260.0, 220.0))
    pen.lineTo((300.0, 200.0))
    pen.lineTo((260.0, 180.0))
    pen.lineTo((300.0, 160.0))
    pen.lineTo((260.0, 140.0))
    pen.lineTo((300.0, 120.0))
    pen.lineTo((271.7157287525381, 128.2842712474619))
    pen.lineTo((280.0, 100.0))
    pen.lineTo((260.0, 140.0))
    pen.lineTo((240.0, 100.0))
    pen.lineTo((220.0, 140.0))
    pen.lineTo((200.0, 100.0))
    pen.lineTo((180.0, 140.0))
    pen.lineTo((160.0, 100.0))
    pen.lineTo((140.0, 140.0))
    pen.lineTo((120.0, 100.0))
    pen.closePath()
    """


if __name__ == "__main__":
    import doctest

    doctest.testmod()
