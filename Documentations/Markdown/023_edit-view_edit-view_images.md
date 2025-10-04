### Images

#### Adding Images

All image formats supported by macOS can be added to a glyph layer.
These include JPEG, PNG, PDF, TIFF, and PSD files.
Add an image by dragging the image file over a glyph cell in Font View or over a glyph in Edit View.
Alternatively, choose “Glyph” → “Add Image…” to insert an image file.

In a Glyphs document, only the relative path to an image file is stored.
Thus, it is a good idea to keep images in a subfolder next to the Glyphs file.
If the path to the placed image is outdated or broken, it will be indicated with a missing image symbol:

Toggle the display of images with “View” → “Show Image”.
Images are always displayed for empty glyphs (glyphs without paths or components).

Image files are ignored at export unless exporting a bitmap image font, like an sbix color font.

#### Manipulating Images

By default, images are scaled to a size where one DTP point corresponds to one font unit and placed at the origin point of the layer.
Consider scaling images before importing them into Glyphs when preparing scans.

Move an image by dragging it to the desired position.
When an image is selected, resize it with the bounding box (Cmd-Opt-Shift-B) or the Scale tool  (S).
Rotate an image with the Rotate tool  (R).
The _Transformations_ palette also works for images.

The Info box (Cmd-Shift-I) offers controls for the image position (_{X} and _{Y}) and dimensions ( width and  height) of the selected image.
Rotate the image by changing the degree figure next to the curved arrow .
Clicking the right-pointing arrow  reveals the original image file in Finder.

Click the lock  icon to lock  the image.
A locked image cannot be selected or manipulated.
Unlock an image by Control-clicking or right-clicking the image on the canvas and choosing “Unlock Image”.
Choose “Set Crop to Layer Bounds” from the image context menu to hide the image outside the layer bounds defined by its width, descender, and ascender.
Choose “Reset Crop” to undo such a crop.