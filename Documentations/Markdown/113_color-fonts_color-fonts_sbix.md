### sbix Fonts

See the TrueType Reference Manual for details on `sbix` color fonts.

Apple-style color fonts include an `sbix` table (Standard Bitmap Graphics) containing bitmap data of various resolutions.
Multiple images of various sizes may be assigned to each glyph.
Thus, the device displaying it can pick the most appropriate resolution.

#### Standard Bitmap Graphics

In contrast to the other color font formats covered in this chapter, `sbix` fonts do not use vector but bitmap graphics.
These graphics may be prepared as PNG, JPEG, or TIFF images.

Each glyph contains a single image file.
However, images can be provided for different pixel sizes.
A glyph might contain a 512 × 512 pixel image, but also lower resolution versions at, for example, 128, 32, and 16 pixels.
While a single large image per glyph could be scaled down to fit every size below, including smaller sizes of images presents two advantages:

- Providing images for smaller sizes allows fine-tuning the graphics for low-resolution output. For example, the design might be adapted to read more clearly at smaller pixel sizes.

- If smaller images are not included in the font, the text renderer needs to scale the large images down to the desired font size. This can be slow, especially on low-end devices, and use more energy, which is relevant to mobile devices.

Images are scaled up by the text renderer when using a font size above the largest image dimensions, resulting in blurry glyph images.

#### Preparing Images

Create the graphics in an image editing application and export them at the desired sizes.
This size is measured in pixel units, not in font size units.
For example, export images at heights of 512, 256, 32, and 16 pixels.

The differently sized images for a glyph must all share the same aspect ratio.
This aspect ratio is width ÷ height.
So, if the image version with a height of 512 pixels is 512 pixels wide (512 ÷ 512 = 1, a square), all other images must also be square.
If one image is twice as tall as it is wide (256 ÷ 512 = 0.5), all other images for that glyph must share the aspect ratio of 0.5.

Pro Tip:

For clarity, name image files after their glyph name and pixel size, such as “rainbow 32.png” for “🌈”.

When adding these images to a Glyphs file, they are not copied into the Glyphs file, but merely referenced.
Moving, renaming, or deleting the image files will break these references.
Therefore, it is best practice to place the images in a folder next to the Glyphs file.

#### Adding Images to Glyphs

The master layer does not contain glyph outlines.
However, some software—such as Google Chrome and Adobe Photoshop—use the bounding box of paths on the master layer as a mask for the bitmap images.
Therefore, it is a best practice to place tiny paths in the bottom-left and top-right of the master layer, like here:

These tiny paths can also have their nodes on the same single point, thus hiding the path.
The red node background  that Glyphs shows for overlapping nodes can be ignored in this case.
This bounding box, highlighted in green in the image above, is used by Glyphs to place the images on their color layers.

Color layers for the `sbix` format are named “iColor” layers.
Add iColor layers by clicking the plus  button in the “Layers” palette (“Window” → “Palette”, Cmd-Opt-P) and choosing “iColor” from the context menu on the layer.
The name of an iColor layer includes its size, for example, “iColor 512” or “iColor 24”.

Double-click a layer entry in the “Layers” palette to change its size.
Scale images by changing this iColor pixel size.
Images appear smaller if the entered pixel size is larger than the image, and they appear larger if the entered size is smaller than the image.

Add iColor layers for each image resolution.
Note that changing the width of the master layer also changes the width of all of its iColor layers.

#### Exporting

Glyphs includes the `sbix` table in exported font files if iColor layers are present in the font.
Discard the `sbix` table by adding an Export sbix Table custom parameter to an instance and unchecking it.

Glyphs can convert `sbix` color fonts to SVG color fonts.
This allows the color font to be used in software that supports SVG color fonts, but not `sbix` fonts.
Add the SBIX to SVG custom parameter to an instance and set its value to the desired pixel size at which Glyphs will convert the `sbix` image data to SVG data.
For example, setting this parameter to 128 uses the iColor layers sized at 128 pixels, if any, otherwise the smallest iColor layers above 128, and if there are none at or above that size, the next largest available iColor layers.

Uncheck Export sbix Table and set the SBIX to SVG parameter to export an SVG-only color font.