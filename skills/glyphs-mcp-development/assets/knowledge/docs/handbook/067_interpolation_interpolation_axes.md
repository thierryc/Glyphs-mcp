### Setting up Axes

Define interpolation axes in “File” → “Font Info…” → “Font” → “Axes”.
Click the plus  button next to the “Axes” heading to add a new axis.
An axis has a name, a four-character tag, and a hidden-checkbox.

Click the disclosure  button to pick one of the predefined axes.
Choosing a predefined axis also sets its four-character tag field with the respective value.
The predefined axes are a combination of the registered OpenType design-

variation axes and axes proposed for inclusion in the registry.
Otherwise, define a custom axis (also referred to as a _private_ axis) by setting an arbitrary axis name and a custom four-letter tag.
The tag of a private axis should use four capital letters (A–Z) as not to collide with future registered axes.
For instance, a custom Swash Length axis might use the tag `SWLN`.

Check the “Hidden” checkbox to hide an axis in user interfaces.
If set, this signals to applications using the font that they should not display controls (such as a slider) for this axis.
Hide axes if they are applicable only in specialized software.
Applications may or may not respect this option.
In most cases, this checkbox should be left unchecked.