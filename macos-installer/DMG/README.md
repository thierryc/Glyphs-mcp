# DMG presentation assets

The Finder window uses a **680 × 420 point** content canvas. The packaged
`background.tiff` contains **680 × 420** and **1360 × 840** representations so
Finder can render the text sharply at both standard and Retina scale.

`background.svg` is the editable source. Regenerate the 1x PNG, 2x PNG and
multi-resolution TIFF with:

```sh
./scripts/render_dmg_background.sh
```

The packaging script places the app at `(170, 194)` and the Applications alias
at `(510, 194)`. Preserve clear areas around those coordinates and around the
Finder labels immediately below them. The arrow and explanatory copy belong in
the background; the app and Applications icons are real Finder items. The
positions are applied to the Finder icon-view window, then the image is reopened
and packaging fails unless Finder persisted both exact coordinates. Do not set
positions on the mounted folder object: Finder may silently keep its default
alphabetical layout instead.

The local `SKIP_NOTARIZATION=1` build is only for layout and installation
testing. The final release DMG must still pass the normal signing, notarization,
stapling, and release verification gates.
