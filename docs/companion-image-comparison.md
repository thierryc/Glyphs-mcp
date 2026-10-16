# Image comparison in the companion

The shared project diff viewer previews PNG, JPEG and WebP changes in any
project. It compares the committed `HEAD` version with the current working
file, including the combined result of staged and unstaged changes. Added,
deleted, renamed and untracked image files use the same viewer.

The toolbar reuses the glyph diff viewer's native **Before / Both / After**
segmented control, spacing and zoom controls. **Both** reveals Before on the
left and After on the right with a draggable divider. A native slider provides
an accessible alternative. Zoom out, percentage, zoom in and Fit use the same
presentation as glyph diffs. Layer and Guides are specific to glyphs and do not
appear for raster images.

Both is offered only when two valid images are available. Selecting a missing
or unreadable version shows an explanation. Different dimensions retain a
common scale and top-left alignment; transparent pixels use an opaque
checkerboard so one version never leaks through the other. Animated formats
show their first frame.

Reading and previewing never changes source files or the Git index. The reader
refuses symlinks, nonregular files and unsafe paths. Encoded input is limited to
16 MiB and decoded dimensions to 32 million pixels. ImageIO normalizes EXIF
orientation and generates previews up to 2048 pixels on the longest side.
The dimensions displayed are the original oriented dimensions; zoom refers to
that original canvas. Comparison cache entries are bounded in count and memory.

This first version provides switching and wipe comparison. It does not compute
pixel differences or a percentage of changed pixels.

Verification uses disposable Git repositories and generated image fixtures,
including real PNG, JPEG and WebP data, EXIF orientation, transparency, invalid
and oversized input, symlinks and different image dimensions. A standalone
SwiftUI fixture exercises the actual viewer without installing or restarting
the companion, sidecar or Glyphs.
