### Smart Components

Smart components allow for variation of design properties within a single component glyph.
Each smart component can have its own set of variation properties such as _width_, _height_, _angle_, _roundness_, or any other arbitrary design feature that can vary along an axis.
In this way, smart components work like multiple masters or a variable font, but with the variation axes exclusive to a component.

Smart components were initially designed for Asian scripts, where shapes are frequently reused with slight modifications, such as the strokes in CJK fonts or the components of the Tibetan script.
This concept—reusable components with property variations—has proven useful for various scripts and glyphs.

#### Setting up Smart Glyphs

Above: The two layers of a _part.arrow smart glyph.
Below: The “Layers” palette for the smart glyph.

The glyph of a smart component is called a smart glyph.
All CJK radical and Korean base glyphs are smart glyphs.
In addition, all glyphs with a name starting with “_smart.” or “_part.” are smart glyphs.

The different forms of a smart glyph (for example, Narrow and Wide or _Sharp_ and _Rounded_) are placed on smart layers.
Click the plus  button in the bottom-left of the “Layers” palette to create a new layer.
New layers are named after the current date and time, but that is not a good description for a smart layer.
Double-click the smart layer name and change it to a more descriptive one such as “Narrow”, “Low Contrast”, “Small”, or any other name that best describes the variation.
For instance, for a _part.arrow glyph with a Width property, draw a normal arrow on the Regular master layer and a narrow version of the arrow on an additional layer aptly named “Narrow”.
Note that smart layers need to be compatible with the master layer.
For more on layer compatibility, see Outline Compatibility.

Smart glyph properties control how the smart component interpolates between the different layers.
Add a property by opening the “Smart Glyph Settings” with “Edit” → “Info For Selection” (Cmd-Opt-I) or by choosing “Show Smart Glyph Settings” from the component context menu.
It is split into two tabs: “Properties” and “Layers”.

##### Smart Glyph Properties Settings

Create a new property by clicking the plus  button located in the bottom-left of the “Properties” tab.
Smart glyph properties are similar to font axes.
They have a name as well as minimum and maximum values.
The name can be chosen freely and may be unrelated to the layer names or axes names of the font.
The names “Width” and “Height” have a special meaning; see Width & Height Properties for details.

The minimum and maximum values can be any number range, but the minimum needs to be less than the maximum.
Values can be negative.
The default range of 0–100 works well for abstract properties such as “Contrast” or “Curviness”.
If the variation property is less abstract and related instead to font units—such as “Height” or “Descender Depth”—consider using measurements as minimum and maximum values.
Continuing the _part.arrow example, if the normal arrow is 855 units wide and the arrow on the “Narrow” layer is 375 units wide, add a “Width” property with a minimum of 375 and a maximum of 855.

Note that smart components can be interpolated _and extrapolated_.
This allows the usage of values below the minimum and above the maximum.
For example, a _part.arrow component with a “Width” property ranging from 375 to 855 can also be used with a “Width” value of 300 or 900.
Extrapolation works well for simple variations such as the tail of an arrow getting longer and shorter, but might produce less desirable results for more complex smart components such as the arch of an “n” getting wider and narrower.

Use a minimum of 0 and a maximum of 1 for properties that should not interpolate and instead only be used as an on/off toggle.

##### Smart Glyph Layers Settings

The “Layers” tab connects smart properties with smart layers.
The sidebar shows all smart layers of the glyph.
Select a layer and set whether it belongs to the minimum or maximum value.
If a layer is unrelated to a property, do not check any of the two values.
For instance, for a glyph with two layers—“Regular” and “Narrow”—and a “Width” property, check the minimum Width value for the Narrow layer and the maximum Width value for the Regular layer.

A setup with multiple properties does not require a layer at all extremes.
For example, a smart glyph with two properties—“Width” (range 375–855) and “Height” (range 80–360)—only requires the following three layers:

|  | Width | Height |
|---|
| Regular |  375  |  80  |
| Wide |  855  |  80  |
| Tall |  375  |  360  |

 Note that a layer at both maximum values (Width of 855 and Height of 360) is not required.
Glyphs infers it from the Wide and Tall layers.
Consider adding a layer at both extremes only if the inferred outlines are not as desired.

#### Using Smart Components

Add a smart component like any other component (as described in Building Composites).
A smart component is indicated by a “Smart” badge in its Info box.

“Smart Component” dialog as shown with “Edit” → “Info for Selection” (Cmd-Opt-I) for a selected component.

If the Info box is not visible, select the smart component and check “View” → “Show Info” (Cmd-Shift-I).
Click the “Smart” badge in the Info box or choose “Edit” → “Info for Selection” (Cmd-Opt-I) to configure the selected smart components.

If the Palette is visible (“Window” → “Palette”) and “View” → “Show Info” is checked, the smart component settings are also visible at the bottom of the Palette.

Use the slider  to set the setting of a property anywhere from the minimum to the maximum value.
Use the number field to input any value, which might also extrapolate beyond the minimum and maximum values.
If the min/max values are 0/1, a checkbox  is displayed instead.

#### Width & Height Properties

Name smart glyph properties “Width” or “Height” (with a capital letter) to control them with the bounding box.
Select “View” → “Show Bounding Box” (Cmd-Opt-Shift-B) and click on a smart component to show its bounding box.
Resizing the bounding box horizontally changes the “Width” property; resizing vertically changes the “Height” property.
Resizing the bounding box is impossible for a smart component with neither a Width nor a Height property.

#### Smart Handles

**Left:** Placing anchors with the names of properties on all layers.
**Right:** Moving a knob to adjust smart settings.

Smart handles allow properties to be modified using control handles placed on the smart glyph.
Place an anchor with the name of a smart glyph property on every smart glyph layer.
The anchor names must match the name of the property exactly, including capitalization.
On smart glyph layers affecting the property, move the anchor to match the modified outlines.
These anchors do not need to be added for all properties.

When using the smart glyph as a component, gray handles will appear when the component is selected.
Click and drag a handle to change its property value.