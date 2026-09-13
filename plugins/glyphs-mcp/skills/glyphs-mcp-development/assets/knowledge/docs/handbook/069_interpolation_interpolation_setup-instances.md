### Setting up Instances

In “File” → “Font Info…” → “Exports”, click the plus  button located in the bottom-left of the window to add a new instance.
See Font Info: Exports for details on adding and configuring instances.

#### Static Instances

Static instances (“” → “Add Instance” and “Add Instance for each Master”) are exported as single font files.
The “Axes Coordinates” of an instance need to be set up as described in Exports: Axes Coordinates.
Note that the “Weight Class” and “Width Class” fields are independent of any axis coordinates; see Weight & Width.

Static instances are also included in variable fonts as a set of predefined axis configurations.
This allows a font user to pick a predefined instance from a font style menu instead of configuring the variation axes manually.
Instances that are outside the designspace (extrapolated) cannot be included in variable fonts.

Many custom parameters, including filters, are applied only to static instances when exported as single files, not when included in variable fonts.
This is because, in a variable font, all instances need to be compatible, which means they have compatible outlines, the same glyphs, and the same features.

#### Variable Font Settings

A variable font setting (“” → “Add Variable Font Setting”) controls the export settings of a variable font.
Adding multiple variable font settings will export multiple variable fonts with different configurations.
Ensure that they have different names, so they do not conflict on export.

Since a variable font setting operates on the entire variable font, it can use the custom parameters that are not applied to its instances.
These include filters, removing glyphs, and adding features.
However, these custom parameters may still lead to incompatible outlines, which is reported as an error when exporting the variable fonts.

#### Subsetting the Designspace

Add a Disable Masters custom parameter to a variable font setting to export a subset variable font.
Write the names of font masters into the text field of the parameter, separated by a comma and a space (“, ”).
These masters will not contribute to the exported variable font.
Axes which are not used by the remaining masters are removed from the variable font.