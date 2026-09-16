# DMG presentation assets

The Finder window uses a **680 × 420 point** content canvas. Keep
`background.png` at exactly **680 × 420 pixels** so Finder displays it at the
intended size without scaling or cropping.

`background.svg` is the editable source. Regenerate the PNG with:

```sh
./scripts/render_dmg_background.sh
```

The packaging script places the app at `(170, 194)` and the Applications alias
at `(510, 194)`. Preserve clear areas around those coordinates and around the
Finder labels immediately below them. The arrow and explanatory copy belong in
the background; the app and Applications icons are real Finder items.

The local `SKIP_NOTARIZATION=1` build is only for layout and installation
testing. The final release DMG must still pass the normal signing, notarization,
stapling, and release verification gates.
