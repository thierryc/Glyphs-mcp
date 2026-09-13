### Custom Parameters

Custom parameters provide additional settings and are identified by their property and have a value.
In this appendix, the properties are printed in bold.
The short description next to it explains the respective values and the function of the parameter.
Parameters can be added to the “Custom Parameters” field of the Font, Masters, and Exports tab of “File” → “Font Info” (Cmd-I).

Enabled parameters are displayed in black; disabled parameters are displayed in gray.
Quickly disable a parameter by unchecking the checkbox to the left of its property name.

Custom parameters in camelcase (“exampleName”) are defined in the UFO specification and change the font information.
In contrast, capitalized ones (“Example Name”) are specific to Glyphs and usually change something in the font (for instance, run a filter on the outlines).
UFO parameters follow the naming convention for Font Info properties outlined in the UFO 3 specification published in March 2012.
Glyphs also makes use of a simplified naming convention.
Wherever possible, leave out the prefix of the keyword.
For example, instead of openTypeNameDescription, use description, or blueScale instead of postscriptBlueScale.
Both long and short versions work side by side.

Add Class

  string  Add an OpenType class to the font. The first word must be the class name (without the at sign), followed by a semicolon, and the new class code.

Add Feature

  string  Add an OpenType feature to the font. The first word must be the feature tag, followed by a semicolon, and the new feature code. It will be put at the end of the list, so it may not be in the right order.

Add Prefix

  string  Add an OpenType prefix to the font. The first word must be the prefix name, followed by a semicolon, and the new prefix code.

ascender

  string  Overrides the Ascender value for a certain script. The values will be preferred for glyphs associated with the script in the Edit view. As value, enter the lowercase name of the script, followed by a colon and the value, e.g., `cyrillic: 720`. Use multiple parameters for multiple scripts.

Autohint

  boolean  Forces autohinting for the given instance, regardless of the setting in the Export dialog

Axis Location

  list  Remaps a master or instance from the internal design space coordinates to values that are exposed in a variable font user interface (“external coordinates”). This can be useful if your internal design space coordinates do not already adhere to the suggestions of the OpenType specification.

Axis Mappings

    Creates an `avar` table by mapping internal design coordinates to external coordinates exposed to the user. Put the internal coordinate into the left column, and the external coordinate in the right column. Or, add and edit values by clicking and dragging in the chart. The range for the internal coordinates is determined by the actual axis positions of the masters in “Font Info” → “Masters,” whereas the range for external coordinates is determined by the _Axis Location_ parameters in “Font Info” → “Masters.”

Note that axis mappings work only _per axis,_ and cannot be adjusted for different positions of _other_ axes. This is a limitation of the `avar` implementation, so you may have to compromise on one of the mappings or pick an average value as the target mapping.

blueFuzz

  integer  BlueFuzz value. This corresponds to the Type 1/CFF BlueFuzz field. From the Type 1 specification: The number specifies the `units to extend (in both directions) the effect of an alignment zone on a horizontal stem. If the top of a horizontal stem is within BlueFuzz units (in character space) outside of a top-zone, the interpreter will act as if the stem top were actually within the zone; the same holds for the bottoms of horizontal stems in bottom-zones. The default value of BlueFuzz is 1.

Adobe themselves state that BlueFuzz was intended to compensate “for slightly inaccurate coordinate data.” They therefore suggest adjusting the alignment zones themselves as well as explicitly setting BlueFuzz to zero. “Because a non-zero value for BlueFuzz extends the range of alignment zones, alignment zones must be declared at least (2 × BlueFuzz + 1) units apart from each other. Therefore, a default BlueFuzz value of 1 implies that alignment zones should be at least 3 units apart from each other.”

blueScale

  float  PostScript BlueScale value. This corresponds to the Type 1/CFF BlueScale field. Controls the font size until which overshoot display is suppressed. Calculated as (pointsize at 300 dpi – 0.49) ÷ 240, e.g., 0.039625 for 10 points at 300 dpi. If you do not set the value yourself, blueScale defaults to 0.037, which corresponds to 9.37 points at 300 dpi or 39 pixels per em. This means that, in this case, overshoots will be visible if at least 40 pixels are used to display an em. The maximum blueScale value depends on the sizes of your alignment zones. The maximum pointsize at 300 dpi is calculated as 0.49 + 240 ÷ largest alignment zone size, which corresponds to a PPM (size in pixels per em) of 2.04 + 1000 ÷ largest alignment zone size. The product of (maximum pointsize – 0.49) × (largest alignment zone height) must be less than 240.

For example, your largest zone is 21 units deep, thus: 2.04 + 1000 ÷ 21 = 49.659, so the maximum PPM at which overshoots can be suppressed is 49. The corresponding maximum pointsize is 0.49 + 240 ÷ 21 = 11.919 points at 300 dpi, thus the blueScale value cannot exceed (11.919 – 0.49) ÷ 240 =  0.04762.

blueShift

  integer  PostScript BlueShift value. This corresponds to the Type 1/CFF BlueShift field. Default value is 7. Extends for very small glyph features beyond the font size indicated by blueScale. Overshoots inside an alignment zone are displayed if: (a) they are equal to or larger than BlueShift and (b) if they are smaller than BlueShift but larger than half a pixel. E.g. blueScale is set to suppress overshoots until 32 PPM, blueShift is 6, overshoots are 12 units deep. The stroke endings are slightly slanted and extend 5 units below the baseline. Between 0 and 32 PPM, the baseline will be kept completely level. Starting at 33 PPM, the overshoots will kick in. But the stroke endings will stay flat, because 5 units do not cover half a pixel until 100 PPM.

capHeight

  string  Overrides the Cap Height value for a certain script. The values will be preferred for glyphs associated with the script in the Edit view. As value, enter the lowercase name of the script, followed by a colon and the value, e.g., `adlam: 680`. Use multiple parameters for multiple scripts.

CJK Grid

  integer  Number of rows and columns of a dotted-line grid displayed when editing CJK glyphs. You can set number of rows and columns separately with the _CJK Grid Horizontal_ and _CJK Grid Vertical_ parameters. No grid is displayed when none of these parameters are set. This parameter can be localized like the _CJK Guide_ parameter.

CJK Grid Horizontal

  integer  Number of columns of a dotted-line grid displayed when editing CJK glyphs. This parameter can be localized like the _CJK Guide_ parameter.

CJK Grid Vertical

  integer  Number of rows of a dotted-line grid displayed when editing CJK glyphs. This parameter can be localized like the _CJK Guide_ parameter.

CJK Guide

  string  Percentage of inset for CJK guide squares, e.g., 10 for 10 percent. If set, Glyphs will display a second square guide for the virtual body in CJK glyphs. You can localize the parameter by preceding the value with the script name, e.g., `kana:5`. If you want to define virtual bodies for more than one script, add more _CJK Guide_ parameters.

codePageRanges

  list  Sets the appropriate bits of the `ulCodePageRange1` and `ulCodePageRange2` entries in the `OS/2` table. “This field is used to specify the code pages encompassed by the font file in the cmap subtable for platform 3, encoding ID 1 (Microsoft platform).” Every activated “code page is considered functional. Each of the bits is treated as an independent flag and the bits can be set in any combination. The determination of “functional” is left up to the font designer, although character set selection should attempt to be functional by code pages if at all possible.”

Color Layers to COLR

  boolean  If turned on, will produce `COLR` and `CPAL` tables with the color information stored in a color setup, from the masters that have a `Master Color` parameter.

Color Layers to SVG

  boolean  If turned on, will produce an `SVG` table with the color information stored in CPAL Color layers, or, in a layered-font setup, from the masters that have a `Master Color` parameter.

Color Palette for CPAL

  integer  Index of the color palette (as defined in the `Color Palettes` parameter) that is supposed to be used for the `CPAL` OpenType table.

Color Palette for SVG

  integer  Index of the color palette (as defined in the `Color Palettes` parameter) that is supposed to be used for the `SVG` OpenType table. Useful only in conjunction with the Color Layers to SVG parameter.

Color Palettes

  list  Define color palettes for export as a `CPAL` OpenType table in “Microsoft-style” CPAL/COLR color fonts. This parameter allows Glyphs to display a preview of color glyphs in Font and Edit view.

Compatible name Table

  boolean  Exports a legacy `name` table as expected by some Mac apps (in particular Quark XPress and FontExplorer). It improves grouping of font styles in the font menu of those apps, but may break functionality elsewhere, especially Microsoft Office. Therefore, caution is advised in the use of this parameter.

compatibleFullNames

    Sets `name` table ID 18, “Compatible Full Name”, a Mac-only name which is intended to be preferred over ID 4 (“Full Name”). If not set, the value for `name` table ID 18 is calculated from Family Name plus space plus Style Name of the respective instance. “On the Macintosh, the menu name is constructed using the FOND resource. This usually matches the Full Name. If you want the name of the font to appear differently than the Full Name, you can insert the Compatible Full Name in ID 18.” **Caution:** since this may lead to a situation where Mac and Windows use different full names for the same font, it may break cross-platform interoperability of documents.

copyrights

    Copyright statement. Overrides the entry in the Copyright field in the Font tab of the Font Info. Corresponds to the OpenType `name` table ID 0, “Copyright notice”.

cvt Table

  string  List of values for the `cvt` (control value table). When you open a TTF in Glyphs, the application will store the existing `cvt` values in this parameter. This is intended to preserve existing TT hinting for reexporting, and certainly not to be edited manually. Remove this parameter if you want to do your own TrueType instructioning.

Decompose Brace Layers

  boolean  In variable font exports, decompose components that point to glyphs with intermediate layers a.k.a. “brace layers”. Default is on.

Decompose Components

  boolean  Decompose all components on export. Useful for situations where the environment cannot handle components correctly, such as eraly implementations of Variable Fonts in legacy macOS versions. Will increase file size. Only makes sense for TrueType fonts; CFF-based fonts will always decompose.

Decompose Components in Variable Font

  boolean  When exporting a (TT-based) variable font, all components will be decomposed to outlines. This option is intended to circumvent a CoreText rendering bug in macOS versions prior to Mojave 10.14.5, which affected the spacing of composite glyphs with changing LSB values under certain circumstances. Since the resulting variable font contains no more components, its file size can be expected to increase dramatically.

Decompose Glyphs

  list  At export, decomposes the composite glyphs listed. This can be useful if you want to avoid changing of composites when one of the components is being changed with the Rename Glyphs parameter.

Default Layer Width

  integer  Newly created glyphs and layers will have the specified width rather than the default 600 units, or 1000 units for CJK glyphs, or 200 units for corner components. If you prefix the value with a (lowercase) script name and a colon, the specified layer width will only be applied to glyphs of that script, e.g., `cyrillic: 400` or `adlam: 450`. Add multiple parameters for multiple scripts.

descender

  string  Overrides the Descender value for a certain script. The values will be preferred for glyphs associated with the script in the Edit view. As value, enter the lowercase name of the script, followed by a colon and the value, e.g., `arabic: -300`. Use multiple parameters for multiple scripts.

descriptions

    Description of the font. Corresponds to the OpenType `name` table ID 10: “description of the typeface. Can contain revision information, usage recommendations, history, features, etc.”

Design Grid

  string  Number of rows and columns of a dotted-line grid. Mostly used for CJK design. It can take three values: `[script:]horizontal,vertical`

designers

    Name of the designer. Overrides the “Font Info” → “Font” → “Designer” entry for the given instance. Corresponds to the OpenType `name` table ID 9, “name of the designer of the typeface.”

designerURL

  string  The URL of the designer. Overrides the “Font Info” → “Font” → “Designer” → “URL” entry for the given instance. Corresponds to the OpenType `name` table ID 12, “URL of typeface designer (with protocol, e.g., http://, ftp://).”

Disable autohinting for glyphs

  list  Excludes listed glyphs from the PostScript autohinting at export time. (TT autohinting cannot be disabled on a per-glyph basis.) This can be useful if some glyphs do not lend themselves for hinting, e.g., ornaments.

Disable Masters

  list  Disables all specified masters. Intended mainly for specific production workflows, or for testing purposes, e.g., to see if interpolation still behaves as expected if you leave out one of the intermediate masters.

Disable Subroutines

  boolean  If set, CFF outline subroutinization is disabled when the font is exported. Use this (a) when the font has complex outlines with many nodes and does not export at all, or (b) for testing purposes when the font has many glyphs, e.g., a CJK font, and takes too long to compile every time you export.

DisableAllAutomaticBehaviour

  boolean  Will disable most of the automatic stuff on export.

-  reordering `.notdef` and `space`

-  zero widths for nonspacing marks

Don't use Production Names

  boolean  If checked, Glyphs will not automatically rename glyphs of the final font file according to the internal glyph database, but export the current glyph names. Some applications and systems, amongst which the text engine of OS X 10.4, expect the AGL naming scheme, though. This is equivalent to the “File” → “Font Info” → “Other Settings” → “Use Custom Naming” setting, and intended for users who want to employ their own custom naming scheme.

EditView Line Height

  float  Sets the line height for text set in an Edit tab. Useful if you have unusual vertical metrics, and the default leading seems inappropriate. Has no effect on the exported font file.

Elidable STAT Axis Value Name

  string  Declares the style name of the instance as elidable for the axis specified in the parameter’s value. As value, use the four-letter tag of the respective axis. Typically, you will add this parameter in the regular style, and you will add one for each axis for which the name is an elidable display string. Example: In a two-axis setup, an instance called Regular has two Elidable STAT Axis Value Name parameters, one with `wght` and one with `wdth` as parameter values. A display string is deemed elidable if it is left out when combined with other display strings. Usually this is the case for default-style names like “Regular”, “Normal”, or the like. The semibold weight combined with regular width is usually just called “Semibold”, not “Semibold Regular”; or the normal weight in combination with the italic style is simply called “Italic”, not “Regular Italic”. Thus, the display name “Regular” is considered elidable.

Enforce Compatibility Check

  boolean  Forces compatibility checks between all masters. Compatibility is only checked for a pair of masters if they are both required for interpolating one of the instances defined in “File” → “Font Info” → “Instances.” Useful if you have no instance between certain masters, but still need to keep them compatible, e.g., for a variable font.

Export AAT

  boolean  Toggles the export of Apple Advanced Typography (AAT) instructions as entered in “File” → “Font Info” → “Features” → “Prefix” → “morx.” If `morx` instructions are present in Font Info, they will be compiled into a `morx` table by default. This parameter is intended as an option to prevent its export, and thus create a pure OpenType font.

Export COLR Table

  boolean  Toggles the export of `CPAL` and `COLR` tables. If all conditions are met, `CPAL` and `COLR` tables will be compiled and exported by default, though. This parameter is intended as an option to prevent their export.

Export Folder

  string  Adds a subfolder to the default export destination. Please make sure to use only characters that are valid in folder names.

Export Glyphs

  list  Exports all glyphs listed, regardless of whether the glyph was set to export or not.

Export kern Table

  boolean  On export, will write an old-style `kern` table in addition to the kern feature in the `GPOS` table. Only affects in TrueType exports (i.e., .ttf or TT-flavored webfonts). All group kerning will be expanded into all possible singleton pairs. This means that you will have to subset before using this parameter, otherwise you risk a table overflow. **Use of this parameter is strongly discouraged,** and only makes sense in rare edge cases where support of defunct or legacy software is necessary. **Only use it if you know what you are doing.**

Export Mac Name Table Entries

  boolean  Control if Macintosh name table entries are exported (they are by default). So this is meant to disable the Macintosh names.

Export morx Table

  boolean  Inserts a `morx` (“extended glyph metamorphosis”) AAT table into the exported font. Takes the contents of a prefix with the name `morx` in “File” → “Font Info” → “Features,” written in MIF code (metamorphosis input file). For this to work, the ftxenhancer command line tool of the Apple Font Tools must be installed. For more information, refer to the documentation included with the Apple Font Tools.

Export OpenType

  boolean  Toggles the export of most OpenType tables. If disabled, and if `morx` data is entered in “File” → “Font Info” → “Features” → “Prefix,” will export a pure AAT font.

Export PostScript Hints

  boolean  If set, will force export of PostScript hinting (default). Can be used for suppressing PostScript hints when its boolean value is turned off.

Export sbix Table

  boolean  Toggles the export of an `sbix` table. If all conditions are met, an `sbix` table will be compiled and exported by default, though. This parameter is intended as an option to prevent its export.

Export STAT Table

  boolean  Toggles the export of the `STAT` table. A `STAT` table will be compiled and exported by default, though. This parameter is intended as an option to prevent its export.

Export SVG Table

  boolean  Toggles the export of an `SVG` table. An `SVG` table will be compiled and exported by default, though. This parameter is intended as an option to prevent its export.

Export TrueType Hints

  boolean  If set, will force export of TrueType hinting (default). Can be used for suppressing TrueType hints when its boolean value is turned off.

Export vmtx Table

  boolean  Forces or suppresses the export of a `vmtx` (“Vertical Metrics”) table. Can be useful if you have top and bottom sidebearings set in your glyphs, but want to export a horizontal variant of your font only. OpenType spec: vmtx

Family Alignment Zones

  list  This parameter can help create a more consistent screen appearance at low resolutions, even if the overshoots differ in the individual weights. It is a good idea to reduplicate the alignment zones of the most important font in your family, usually of the Regular or Book instance. A rasterizer will then try to align all weights if the height difference between the individual weight and the family alignment is less than one pixel. Important: For this mechanism to work, family alignment zones must be compatible with the alignment zones set up in the masters.

familyNames

    Font family name. Overrides the entry in the _Family Name_ field in the Font section of the Font Info. Corresponds to the OpenType `name` table IDs 1 and 4. Used to calculate IDs 3, 4 and 6.

Feature for Feature Variations

  string  Define the OpenType feature into which glyph variant substitutions (a.k.a. “Bracket tricks”) are written in OpenType variable fonts. Default is `rvrn`.

fileName

  string  Name for the font file, without the dot suffix, i.e., without `.otf`, etc. Gives you the chance to export two versions of the same font style name without the second file overwriting the first one.

Filter

  string  Triggers Glyphs filters or app functions in an instance, after decomposition of composite glyphs. The values for the built-in filters are as follows:

-  **AddExtremes**

-  **Autohinting**

-  **HatchOutlineFilter;** OriginX: _x_; OriginY: _y_; StepWidth: _distance_; Angle: _angle_; Offset: _thickness_

-  **OffsetCurve;** _x_; _y_; _makestroke_; _position/auto_

-  **RemoveOverlap**

-  **Roughenizer;** _segmentlength_; _x_; _y_; _angle_

-  **RoundCorner;** _radius_; _visualcorrection_

-  **RoundedFont;** _stem_

-  **Transformations;** LSB: _±_‌shift*; RSB: _±_shift*; Width: _±shift_; ScaleX: _percent_; ScaleY: _percent_; Slant: _degrees_; SlantCorrection: _bool_; OffsetX: _amount_; OffsetY: _amount_; Origin: _select_

Replace all words in italics with your values: The boolean values (_makestroke, visual correction, bool_) are 1 for yes and 0 for no. The value for _position/auto_ must be a floating point number where 0.0 represents 0%, and 1.0 stands for 100%, or the string `auto` for _Auto Stroke._ The _stem_ value in the _RoundedFont_ syntax is optional. The _select_ value in the _Transformations_ syntax can be a number from 0 to 4, representing the five options displayed in “Filter” → “Transformations” → “Transform” → “Origin:” cap height (0), half cap height (1), x-height (2), half x-height (3), baseline (4).

If you want a filter to be applied only to some glyphs, add `include:` or `exclude:`, followed by space- or comma-separated glyph names, e.g., `RemoveOverlap; exclude:a,b,c`.

If you are using third-party filters, refer to their documentation for the parameter string. In particular, the include and exclude options may not be available.

If you want to apply filters before decomposition, use these values with a `PreFilter` parameter.

Fit Curve Panel Settings

    Use this parameter to store the minimum and maximum percentages for the _Fit Curve_ panel in the right sidebar. As parameter value, use two numbers, separated by a comma, e.g., “57, 72”. Once set, the parameter value will pick up changes you make in the _Fit Curve_ UI.

fpgm Table Assembly

  string  Assembly code for the `fpgm` (font program) table. When you open a TTF in Glyphs, the application will store the existing fpgm code in this parameter. This is intended to preserve existing TT hinting for reexporting, and certainly not to be edited manually. Remove this parameter if you want to do your own TrueType instructioning.

fsType

  list  A list of bit numbers indicating the embedding type. The bit numbers are listed in the OpenType `OS/2` specification. Corresponds to the OpenType `OS/2` table fsType field. “Type flags. Indicates font embedding licensing rights for the font. Embeddable fonts may be stored in a document. When a document with embedded fonts is opened on a system that does not have the font installed (the remote system), the embedded font may be loaded for temporary (and in some cases, permanent) use on that system by an embedding-aware application. Embedding licensing rights are granted by the vendor of the font. The OpenType Font Embedding DLL Specification and DLL release notes describe the APIs used to implement support for OpenType font embedding and loading. Applications that implement support for font embedding, either through use of the Font Embedding DLL or through other means, must not embed fonts which are not licensed to permit embedding. Further, applications loading embedded fonts for temporary use (see Preview & Print and Editable embedding below) must delete the fonts when the document containing the embedded font is closed.” You can set fsType to one of these five states:

-  _Installable:_ “Fonts with this setting indicate that they may be embedded and permanently installed on the remote system by an application. The user of the remote system acquires the identical rights, obligations and licenses for that font as the original purchaser of the font, and is subject to the same end-user license agreement, copyright, design patent, and/or trademark as was the original purchaser.”

-  _Forbidden:_ “Restricted License embedding: Fonts that have only this bit set must not be modified, embedded or exchanged in any manner without first obtaining permission of the legal owner. Caution: For Restricted License embedding to take effect, it must be the only level of embedding selected.”

-  _Editable:_ “When this bit is set, the font may be embedded but must only be installed temporarily on other systems. In contrast to Preview & Print fonts, documents containing Editable fonts may be opened for reading, editing is permitted, and changes may be saved.”

-  _Preview & Print:_ “When this bit is set, the font may be embedded, and temporarily loaded on the remote system. Documents containing Preview & Print fonts must be opened “read-only;” no edits can be applied to the document.”

-  _Subsetting forbidden:_ “When this bit is set, the font may not be subsetted prior to embedding. Other embedding restrictions also apply.”

gasp Table

    Sets the `gasp` table (“grid-fitting and scan-conversion procedure”) for TrueType fonts. It controls the two PPM thresholds at which the recommended on-screen rendering behavior changes. The `gasp` table contains rendering recommendations for both a traditional grayscale and a ClearType subpixel renderer. However, keep in mind that a renderer may ignore the data stored herein.

“This table contains information which describes the preferred rasterization techniques for the typeface when it is rendered on grayscale-capable devices. This table also has some use for monochrome devices, which may use the table to turn off hinting at very large or small sizes, to improve performance.” The default threshold sizes are 8 and 20 PPM. Because there are two thresholds, three ranges can be differentiated:

-  _no hinting & symmetric:_ Until the first threshold size, no gridfitting is applied, and text is rendered with antialiasing wherever possible. “At very small sizes, the best appearance on grayscale devices can usually be achieved by rendering the glyphs in grayscale without using hints.”

-  _hinting & asymmetric:_ Between the two threshold sizes, the renderer is recommended to apply gridfitting and suppress grayscale. “At intermediate sizes, hinting and monochrome rendering will usually produce the best appearance.” In ClearType, the matter is handled asymmetrically, i.e., vertical gridfitting is applied, while horizontally, subpixel rendering is used.

-  _hinting & symmetric:_ Beyond the thresholds, the rasterizer is instructed to apply gridfitting and render the shapes in grayscale. “At large sizes, the combination of hinting and grayscale rendering will typically produce the best appearance.” The ClearType rasterizer is instructed to apply symmetric smoothing, i.e., to use anti-aliasing in y direction in addition to horizontal subpixel rendering. “At display sizes on screen,[…] this new improvement of the Windows font renderer produces smoother and cleaner-looking type” (Now Read this: The Microsoft Cleartype Font Collection, Microsoft 2004, p. 14).

Get Hints From Master

  string  Defines which master is taken as source of manual PS and TT hints, sometimes also referred to as the “main master”. Hinting in other masters will be ignored. If not set, manually entered hints will be taken from the first master listed in “File” → “Font Info” → “Masters.” This also affects treatment of TTFStems and TTFZones parameters: only in the indicated master, the UI for those parameters will provide the delta and range buttons.

glyphOrder

  list  Sets the order of glyphs in both the working file and the final font. Glyph names need to be separated by newlines. You can copy and paste the content of a List Filter. Glyphs not listed but still in the font will be appended after listed glyphs, in the default order that Glyphs employs.

Grid Spacing

  integer  Set the coordinate precision for the resulting CFF font, in font units. The value corresponds to the quotient of the Grid Spacing value divided by the Subdivision value in “File” → “Font Info” → “Other Settings.” At export time though, any Grid Spacing value smaller than 1.0 will result in coordinate precision a hundred times finer than the default unit-grid rounding. In other words, all parameter values smaller than 1 are equivalent to 0.01. The purposes of this parameter is to avoid too coarse rounding of point coordinates in very thin interpolations. Any Grid Spacing value equal to or larger than 1.0 will result in grid-unit rounding. In other words, it any value greater than 1.0 is equivalent to 1.0. The parameter has no effect on TrueType outlines, which cannot have higher coordinate precision.

Hangul Composition Groups

  list  Defines composition groups for Hangul type design. Pick a key Jamo glyph and similarly formatted variants for automated composition of complex Hangul composites.

Has WWS Names

  boolean  Sets bit 8 of the `fsSelection` entry in the `OS/2` table: According to the OpenType specification, this bit indicates that “the font has `name` table strings consistent with a weight/width/slope family without requiring use of “name” IDs 21 and 22.” This makes sense only if the naming of your font already adheres to the WWS scheme.

hheaAscender

  integer  Height of the ascender as stored in the `hhea` (horizontal header) table. “Typographic ascent (distance from baseline of highest ascender).”

The `hhea` vertical metrics are mainly in use on Mac apps, including browsers on the Mac. Therefore, unless you have to maintain backwards compatibility with legacy software, it is recommended to keep the `hhea` values in sync with the `typo*` values, and make sure that `Use Typo Metrics` (`fsSelection` bit 7) is switched on.

For a detailed discussion of vertical metrics, see the Vertical Metrics tutorial.

hheaDescender

  integer  A _negative_ integer describing the depth of the descender as stored in the `hhea` table. “Typographic descent (distance from baseline of lowest descender).” For a discussion of the `hhea` values, see `hheaAscender`..

hheaLineGap

  integer  The recommended interlinear whitespace as stored in the `hhea` table. “Typographic line gap. Negative values are treated as zero in some legacy implementations.” For a discussion of the `hhea` values, see `hheaAscender`.

Ignore custom GlyphData file

  boolean  If set, will ignore the content of a GlyphData.xml next to the .glyphs file, or in a Info subfolder next to the .glyphs file.

Ignore out of bounds instances

  boolean  Ignore all instances that are outside of the design space (e.g. when subsetting).

Ignore Vertical Hints

  boolean  In a TrueType export, will ignore all stem hints that are linked to a vertical stem definition, as set forth in a `TTFStems` parameter. Makes sense in exports intended for subpixel rendering, or for webfont exports where you want to keep the file size as small as possible. Only affects manual TT hinting, does not apply to TTF Autohint or PS hinting.

Import Font

    Reference a different .glyphs file, and all glyphs of the referenced file that are not in the host font, will be hot-linked, in the order of their layers and masters, as if you had copied the glyphs from one file to the other. The glyphs will be visible and typeable in Font and Edit view, but locked. Useful for splitting design work between multiple users, or sharing smart components between files.

Import Master

    Reference a master in different .glyphs file, and it will be hot-linked into the host file, as if you had added it into “File” → “Font Info” → “Masters.” Interpolation values must be set compatibly in both files. Add one parameter for each master you want to hot-link.

Instance Preview

  list  Changes the preview string of an instance in “File” → “Font Info” → “Instances” from the default “Aang126” to the glyph names listed.

InterpolationWeightY

  float  Vertical interpolation value. In an instance, you can differentiate between interpolation along the x axis and interpolation along the y axis by introducing this custom parameter. For it to take effect, it must differ from the interpolation weight of the instance. Be careful, as this can lead to deformation in diagonals. We advice to keep the InterpolationWeightY close to the normal Weight interpolation value.

E.g., there are two masters at weight 20 and 100, and an instance with a weight interpolation value of 50. The vertical stems look correct, but the horizontals look too thin. They would look right at 60, but then the verticals would appear too thick. So, you keep your instance at 50, but add the custom parameter InterpolationWeightY with a value of 60. Now, the vertical stems (x coordinates) are still interpolated with 50, and the horizontals (y coordinates) with 60.

isFixedPitch

  boolean  Sets the `isFixedPitch` flag in the `post` table. Indicates whether the font is monospaced. Software can use this information to make sure that all glyphs are rendered with the same amount of pixels horizontally at any given PPM size.

**⚠️Danger: Will sync the width of all glyphs with the width of the space glyph** This can be overwritten by adding a `.monospace` number value in the master settings.

Italic Style Linking

  boolean  In the STAT table of variable fonts, adds a Format 3 (style linking) AxisValue for the Italic (ital) axis, linking the Regular (ital=0) to the Italic (ital=1). Should **not** be added to (exclusively) italic fonts. Use this parameter for forcing or suppressing the style linking rather than relying on the built-in automation.

italicAngle

  string  Overrides the Italic Angle value in “File” → “Font Info” → “Masters” either for a certain script or for the whole font. The values will be preferred for glyphs associated with the script in the Edit view. As value, enter the lowercase name of the script, followed by a colon and the value, e.g., `latin: 7`. Use multiple parameters for multiple scripts. The number must be an angle in clockwise degrees from the vertical. Also useful for upright fonts with an angle other than 0°, because macOS may interpret non-zero angles as italic. Affects the CFF ItalicAngle, the post italicAngle, the x offsets of the `OS/2` subscript and superscript values, as well as the hhea caretSlopeRise and caretSlopeRun entries.

Keep Glyphs

  list  List of glyph names for all glyphs that will be kept in the exported font. All other glyphs will be discarded, and kerning and automatic feature code will be updated accordingly. Useful for webfont subsetting in order to achieve smaller file sizes

Can use the same wildcards and category searches as the _Remove Glyphs_ parameter. Uses of _Remove Glyphs_ and _Keep Glyphs_ are mutually exclusive.

Keep Kerning in one Lookup

  boolean  Will attempt to fit all “pair adjustment” kerning into the first GPOS lookup.

This is a workaround for a bug in Microsoft apps where kerning outside the first lookup is ignored. If turned off, Glyphs will default to separating kerning into lookups based on the glyph categories.

Keep Overlapping Components

  boolean  If set, Glyphs does not decompose composite glyphs with overlapping components, such as in Ccedilla. Useful for post-production of TrueType fonts. Has no effect on CFF exports.

Keep Transformed Components

  boolean  Does not decompose composite glyphs with transformed (horizontally or vertically scaled, or vertically shifted) components. Useful for post-production of TrueType fonts. For release-ready production, we do not recommend using this parameter, as it may interfere with TT hinting in affected glyphs. The parameter has no effect on CFF exports.

Keep UI-Font Bounding Box

  boolean  Prevents conjuncts from stacking below in South Asian scripts, by altering the automated feature code for the `cjct` feature accordingly. Useful for intended use in environments where vertical stacking is limited, e.g., in user interfaces, hence the name. Currently only implemented for Oriya.

licenses

    License description. Corresponds to the OpenType `name` table ID 13, the “description of how the font may be legally used, or different example scenarios for licensed use. This field should be written in plain language, not legalese.”

licenseURL

  string  URL for the license. Corresponds to the OpenType `name` table ID 14. “URL where additional licensing information can be found.” Make sure it starts with the protocol specification, typically `https://`.

Link Metrics With First Master

  boolean  If checked, keeps the side-bearings and the kerning of the respective master (in which the parameter is entered) in sync with the first master. In effect, you only have to space and kern the first master. This is especially useful for color fonts or fonts that should not change their metrics throughout their weights.

Link Metrics With Master

  string  Same as Link Metrics With First Master (see above), except that it specifies the name of the master to which kerning and spacing is linked to. If you use this parameter, it is advisable to make sure that all masters have unique names.

Local Interpolation

  string  Apply different interpolation values for specified glyphs. The string must contain a semicolon-separated list of interpolation values for each axis, followed by another semicolon, an `include:` statement and a comma-separated list of glyph names. For a single-axis setup, a single interpolation value suffices. E.g., `120; include: a, g, s` uses interpolation value 120 just for the glyphs a, g and s, while all other glyphs are interpolated according to the interpolation value of the respective instance.

MakeOTF Compatibility Mode

  boolean  If checked, the font created by Glyphs will have its OpenType Layout tables comparable to that created by Adobe’s makeotf program. This can be useful when the feature code for those tables was written with specific makeotf behavior in mind, or if the font is meant to be used in applications that rely on makeotf-compatible output.

manufacturers

    Manufacturer Name. Overwrites the _Manufacturer_ as set in “Font Info” → “Font.” Corresponds to the OpenType `name` table ID 8, “Manufacturer Name”.

manufacturerURL

  string  Manufacturer or Vendor URL. Overwrites the _Manufacturer URL_ as set in “Font Info” → “Font.” Corresponds to the OpenType `name` table ID 11, “URL of font vendor (with protocol, e.g., http://, ftp://). If a unique serial number is embedded in the URL, it can be used to register the font.”

Master Background Color

  string  Sets the canvas color of a master. The canvas assumes the specified color when the respective master is active in Edit view.

Master Background Color Dark

  string  Like `Master Background Color`, but for Dark Mode.

Master Color

  string  Color used for the display of the filled outline of the master in question. Useful also to preview layer fonts (multiple fonts intended to be set on top of each other with different colors). Only effective inside Glyphs, does not export into the OpenType font file.

Master Color Dark

  string  Like `Master Color`, but for Dark Mode.

Master Icon Glyph Name

  string  Name of the glyph that is is to be used for the respective master button displayed in the top left corner of the font window when two or more masters are present in “File” → “Font Info” → “Masters.”

Master Stroke Color

  string  Color used for the display of outlines of the master in question, visible when the Select All Layers tool (Shift-V) is active. Only effective inside Glyphs, does not export into the OpenType font file.

Master Stroke Color Dark

  string  Like `Master Stroke Color`, but for Dark Mode.

meta Table

  list  Add a meta (“Metadata”) table to your font export:

-  **dlng** (Design languages): languages or scripts of the primary user audiences for which the font was designed. This value may be useful for selecting default font formatting based on content language, for presenting filtered font options based on user language preferences, or similar applications involving the language or script of content or user settings.

-  **slng** (Supported languages): languages or scripts that the font is capable of supported. This value may be useful for font fallback mechanisms or other applications involving the language or script of content or user settings. The declarations provided by the `slng` value should be the same as or a superset of those provided by `dlng`. Implementations that use `slng` values in a font may choose to ignore Unicode-range bits set in the OS/2 table.

Each of the entries takes a comma-separated list of `ScriptLangTag` entries. Each `ScriptLangTag` is a hyphen-concatenated string for language, script and region (ISO 3166-1, Alpha-2), compliant to IETF BCP 47, but only script is required. E.g., `Cyrl` for Cyrillic, `sr-Cyrl` for Serbian written in Cyrillic, and `sr-Cyrl-BA` for Serbian written with Cyrillic in Bosnia and Herzegovina. OpenType spec: meta Languages, scripts and regions

Name Table Entry

  string  A custom entry for the OpenType `name` table. The syntax is one of the following three:

-  `nameID; nameString`

-  `nameID platformID; nameString`

-  `nameID platformID encID langID; nameString` If not specified, `platformID` will be assumed as 3, and successively, `encID` as 1 (Unicode), and `langID` as 0x0049 (Windows English). If only `platformID` is specified as 1, then both `encID` and `langID` will be assumed as 0 (Mac Roman, and Mac English).

The `nameID` can be anything except 1, 2, 3, 5, and 6, which cannot be set through this parameter. The `platformID` can either be 1 for Macintosh or 3 for Windows. The optional `encID` and `langID` represent either Windows or Macintosh encoding and language IDs, depending on the platformID. They must be numbers between 0 and 65536, and can be entered in decimal, octal or hexadecimal form. The AFDKO Syntax specification stipulates that “decimal numbers must begin with a non-0 digit, octal numbers with a 0 digit, and hexadecimal numbers with a 0x prefix to numbers and hexadecimal letters a-f or A-F.”

note

  string  Arbitrary note about the font. This is not exported in the final OpenType font, only stored in the .glyphs file. Setting the font note as a custom parameter is equivalent to setting it in “File” → “Font Info” → “Notes.”

Optical Size

  string  Builds the Optical Size OpenType feature (feature tag “size”), with encoded size menu names for Mac and Windows. Requires a string with five semicolon-separated values:

-  _design size:_ size in decipoints (tenths of points) the font was designed for;

-  _subfamily identifier:_ arbitrary integer; different fonts with the same number can be grouped together in an optical size submenu, if the software supports it;

-  _range start:_ decipoint size of the size above which the font is supposed to be used for;

-  _range end:_ decipoint size of the size until (and including) which the font is supposed to be used for;

-  _size menu name:_ submenu name for the optical size, e.g., “Display”, “Subhead”, “Small”, or “Caption”.

_Example:_ “100; 1; 69; 120; Ten” will create a size feature that specifies 10 points as the intended design size, the range in which it is supposed to be used is 7 to 12 points, and the optical size name is “Ten”. Other fonts that use 1 as subfamily identifier and “Ten” as name, can be grouped together.

Optimize Variable Deltas

  boolean  Will drop OpenType Variation deltas from a contour if none of its nodes moves more than half a unit. Default is on. Set this parameter to off in order to also keep low-significant deltas.

panose

  list  Once you click in the Value field, a dialog will appear that allows you to determine the setting for each category in the PANOSE specification. This corresponds to the ten “panose” fields in the OpenType `OS/2` table. “This 10 byte series of numbers is used to describe the visual characteristics of a given typeface. These characteristics are then used to associate the font with other fonts of similar appearance having different names.[…] The PANOSE values are fully described in the PANOSE “greybook” reference, currently owned by Monotype Imaging. The PANOSE definition contains ten digits each of which currently describes up to sixteen variations. Windows uses bFamilyType, bSerifStyle and bProportion in the font mapper to determine family type. It also uses bProportion to determine if the font is monospaced. If the font is a symbol font, the first byte of the PANOSE number (bFamilyType) must be set to “pictorial.” ” At the time of this writing, PANOSE is not required to make a font work anywhere, and, to our knowledge, is hardly in use.

Point To Unit Ratio

  float  Integer number that defines how many font units are equivalent to one DTP point. Determines the export scale of PDFs, including artwork copied into the clipboard. Useful for exchanging vector data with third-party drawing apps, such as Affinity Designer or Sketch.

Post Table Type

  integer  Version of the `post` table built into the instance, the default is 2 for TTF, and 3 for CFF fonts.

postscriptFontName

  string  PostScript name of the font. Corresponds to the OpenType `name` table ID 6. Should be ASCII-only, short (for maximum backwards compatibility less than 30 characters long), and no whitespace allowed, e.g., “MyFont-BoldCdIt”. Do not confuse with postscriptFullName (see below).

“The FontName generally consists of a family name (specifically, the one used for FamilyName), followed by a hyphen and style attributes in the same order as in the FullName. For compatibility with the earliest versions of PostScript interpreters and with the file systems in some operating systems, Adobe limits the number of characters in the FontName to 29 characters. As with any PostScript language name, a valid FontName must not contain spaces, and may only use characters from the standard ASCII character set. If abbreviations are necessary to meet the 29 character limit, the abbreviations should be used for the entire family” (Adobe Technote #5088).

Adobe recommends these abbreviations for style names:

-  **Bd** for Bold

-  **Bk** for Book

-  **Blk** for Black

-  **Cm** for Compressed

-  **Cn** for Condensed

-  **Ct** for Compact

-  **Dm** for Demi _(prefix)_

-  **Ds** for Display

-  **Ex** for Extended

-  **Hv** for Heavy

-  **Ic** for Inclined

-  **It** for Italic

-  **Ks** for Kursiv _(German for: Italic)_

-  **Lt** for Light

-  **Md** for Medium

-  **Nd** for Nord _(style name introduced for Antique Olive)_

-  **Nr** for Narrow

-  **Obl** for Oblique

-  **Po** for Poster

-  **Rg** for Regular

-  **Sl** for Slanted

-  **Sm** for Semi _(prefix)_

-  **Su** for Super

-  **Th** for Thin

-  **Ult** for Ultra _(prefix)_

-  **Up** for Upright

-  **X** for Extra _(prefix)_

postscriptFullNames

    Name to be used for the FullName field in `CFF` table as well as for name table ID 4 (full font name). This is the complete name of the font as it is supposed to appear to the user, and is thus allowed to contain spaces, e.g., “My Font Bold Condensed Italic”. Do not confuse with postscriptFontName (see above).

Some systems match the family name “against the FullName for sorting into family groups.” Therefore, the family name “must match the corresponding portion of the FullName, and be suitable for display in font menus. All fonts that are stylistic variations of a unified design should share the same FamilyName.[…] The FullName begins with a copy of the FamilyName and is completed by adding style attributes — generally in this sequence: weight, width, slope, optical size” (Adobe Technote #5088). The full name “would typically be a combination of name IDs 16 and 17” (typographic family and subfamily names), “without needing any additional qualifications regarding “Regular””. OpenType spec: name ID 4

preferredFamilyNames

    Typographic (a.k.a. “preferred”) family name. Corresponds to name ID 16 in the OpenType `name` table. Setting this parameter only makes sense if it is different from the Family Name (name ID 1) as set in “File” → “Font Info” → “Font.”

“The typographic family grouping doesn’t impose any constraints on the number of faces within it, in contrast with the 4-style family grouping (ID 1), which is present both for historical reasons and to express style linking groups. If name ID 16 is absent, then name ID 1 is considered to be the typographic family name.”

preferredSubfamilyNames

    Typographic (a.k.a. “preferred”) subfamily name. Corresponds to name ID 17 in the OpenType `name` table. Setting this parameter only makes sense if it is different from the Style Name (name ID 2) as set in “File” → “Font Info” → “Instances.”

“This allows font designers to specify a subfamily name within the typographic family grouping. This string must be unique within a particular typographic family. If it is absent, then name ID 2 is considered to be the typographic subfamily name.”

PreFilter

  string  Same as Filter, but applied before decomposition. Only applies to static fonts.

prep Table Assembly

  string  Assembly code for the `prep` (Pre-Program or Control Value Program) table. When you open a TTF in Glyphs, the application will store the existing prep code in this parameter. This is intended to preserve existing TT hinting for reexporting, and certainly not to be edited manually. Remove this parameter if you want to do your own TrueType instructioning.

Prevent Name ID

  string  Will prevent the export of the specified name table entry.  Add multiple parameters for multiple name IDs. E.g. if you want Glyphs not to export IDs 16 (Typographic Family Name) and 17 (Typographic Subfamily Name), add two of these parameters, once with 16 and once with 17 as value.

Preview Ascender

  float  Master parameter for the distance between baseline and the upper edge of the preview in font units. Useful for scaling the preview at the bottom of the Edit View or in the Preview Panel when you have large ascenders that would otherwise be cut off. The default is 1000.

Preview Descender

  float  Similar to `Preview Ascender`, a master parameter for the distance between baseline and the lower edge of the preview in font units. Defaults to `winAscent` if present, or otherwise, the Descender value set in “File” → “Font Info” → “Masters.”

Propagate Anchors

  boolean  Enable or disable the propagation of top and bottom anchors in composites. This means that top and bottom anchors in the base glyphs of components “shine through” to the composite, unless an anchor with the same name is present in the composite glyph. That way, they enable mark-to-base and mark-to-mark attachment for the composite without needing to add and manage additional anchors. Default is on. Primary use for this parameter is for suppressing generation of `mark` and `mkmk` rules for composites.

Reencode Glyphs

  list  Takes a list of `glyphname=unicodevalue` pairs, e.g., `smiley=E100`, `logo=E101`, etc. Assign _multiple_ Unicode values with a comma as separator, e.g., `hyphen=002D,2010`. The parameter assigns the Unicode value to the glyph with the specified name at export. Should the Unicode value in question already be assigned to another glyph, the Unicode value of that other glyph will be deleted, but all production names will remain intact. It will _remove_ a glyph’s Unicode assignment if the Unicode value is left out, e.g., `f_f_i=` and `f_f_j=` will strip f_f_i and f_f_j from their Unicode value.

Remove Classes

  list  Prevents the export of the OpenType classes mentioned in the list. Useful for removing manually written classes when glyphs are removed from the font through the subsetting parameters. Note that automatic classes are removed automatically at export if the triggering glyphs are not in the font anymore, e.g., because they were removed or renamed with parameters.

Remove Features

  list  Prevents the export of the OpenType features mentioned in the list. Useful when a glyph name suffix triggers Glyphs to generate a feature you do not want in the font, or you just want to disable a manually added feature for an instance. Note that automatic features are removed automatically at export if the triggering glyphs are not in the font anymore.

Remove Glyphs

  list  Will prevent the glyphs and groups of glyphs mentioned in the list from being exported into the font. Automatically generated OpenType features respect changes in the glyph structure, e.g., if you remove all smallcap glyphs, then it will not auto-generate the `smcp` or `c2sc` features. Useful for subsetting. Per line, you can use:

-  **glyph name:** the full unabridged glyph name as it appears in Font view. You can copy a list of glyph names by invoking the context menu on a glyph selection and choosing “Copy Glyph Names” → “One per line.”

-  **wildcard:** use an asterisk before, inside or after a string. Examples:

-  `*ogonek` will find Aogonek, aogonek, Eogonek, eogonek, etc.

-  `K*` will find K, Kcommaaccent and K.ss01.

-  `H*.ss01` will find H.ss01, Hbar.ss01 and Hcircumflex.ss01.

-  **category:** use the `category=value` syntax to match glyphs dynamically. If `value` is a string, you can use wildcards. Possible categories are:

-  `name` The glyph name, equivalent to the glyph name searches described above.

-  `unicode` The first Unicode value of the glyph, e.g., `unicode=03*` excludes all glyphs that have Unicode values between 0300 and 03FF.

-  `note` The note of the glyph, e.g., `note=*delete*` will remove all glyphs that have the word delete in their glyph note.

-  `script` The writing system that is assigned to the glyph, e.g., `script=thai` will remove all Thai glyphs from the font. The spelling of the script is case-sensitive and needs to be exactly as displayed in “Window” → “Glyph Info.”

-  `category` The group the glyph belongs to as displayed in “Window” → “Glyph Info,” e.g., `category=Symbol` will remove all glyphs defined as symbol.

-  `subCategory` The subcategory as displayed in “Window” → “Glyph Info,” e.g., `subCategory=Lowercase` will remove all lowercase glyphs from the exported OpenType font.

-  `production` The production name the glyph is assigned at export.

-  `leftMetricsKey`, `rightMetricsKey`, `widthMetricsKey`, `topMetricsKey`, `bottomMetricsKey`, `vertWidthMetricsKey` The metrics key for LSB, RSB, width, top, bottom or vertical width, e.g., `widthMetricsKey=*.tf*` removes all glyphs where the width is synced with a tabular figure.

-  `leftKerningGroup`, `rightKerningGroup`, `topKerningGroup`, `bottomKerningGroup` The kerning group of a glyph, e.g., `leftKerningGroup=s` removes all glyphs that have a left kerning group called “s”.

-  `colorIndex` The color index of CPAL/COLR layers. E.g., assume you defined a color palette with blue at color index 2, then `colorIndex=2` would remove all blue shapes from the exported color font.

-  `countOfLayers` Number of layers a glyph has. E.g., `countOfLayers=4` removes all glyphs that have 4 layers (including the master layers).

-  `mastersCompatible` Whether the glyph is interpolatable through all masters or not. E.g., `mastersCompatible=0` removes all incompatible glyphs from the export.

-  `export` Whether the glyph is set to export or not. This also affects glyphs that are contained as components in others. E.g., `export=0` will remove all non-exporting glyphs from the export, including components if the referenced base glyph is not exporting, as well as corners, caps and smart glyphs.

-  `isAnyColorGlyph` Whether the glyph is a COLR/CPAL, sbix, or full color glyph or not, e.g., `isAnyColorGlyph=0` removes all non-color glyphs from the font.

-  `isAppleColorGlyph` Whether the glyph has an iColor layer for the `sbix` table or not.

-  `hasSpecialLayers` Whether the glyph has a bracket or brace layer or not, e.g., `hasSpecialLayers=1` will remove all glyphs with a bracket or brace layer.

Remove post names for webfonts

  boolean  Removes glyph names in the webfont export, resulting in smaller file sizes.

Remove Prefixes

  list  Takes a list of names for OT feature prefixes as defined in “File” → “Font Info” → “Features.” The code in the prefixes will be kept from being compiled and inserted in the exporting OpenType font.

Rename Glyphs

  list  Will exchange the glyphs mentioned in the value with each other. Takes a list of rename strings of the form `oldname=newname`, e.g. `e.bold=e, g.alt=g`. The glyph previously stored as newname will now be called oldname and vice versa. The parameter will update composites that employ the glyphs involved, update automatic features where necessary, and also exchange the Exports attributes of glyphs. If you want to avoid the export of one the glyphs, make sure that either their Exports attributes are set accordingly, or use the `Export Glyphs` parameter.

Replace Class

  string  Replaces OpenType class code with custom code. The first word must be the class name (without the at sign), followed by a semicolon, and the new class code. Works only if the class exists in “File” → “Font Info” → “Features.” This is only necessary for manually set up classes. Automatically generated classes update automatically.

Replace Feature

  string  Replaces the content of an OpenType feature with the code specified. The first four letters must be the feature name (such as `liga`), followed by a semicolon and the new feature code. Works only if the feature exists in “File” → “Font Info” → “Feature.”

Replace Prefix

  string  Replaces OpenType feature code listed under “File” → “Font Info” → “Features” → “Prefix.” The value must consist of the prefix name, exactly as entered in “Font Info” → “Features,” followed by a semicolon and the replacement code.

ROS

  string  Sets the ROS (Registry, Ordering, Supplement) for fonts with a Character To Glyph Index Mapping Table (`cmap`). Currently available values are the public ROSes:

-  `Adobe-CNS1-6`

-  `Adobe-GB1-5`

-  `Adobe-Japan1-3`

-  `Adobe-Japan1-6`

-  `Adobe-Korea1-2`

-  `Adobe-Identity-0` If you use `Adobe-Identity-0`, a `GSUB` table will be generated from the available OpenType features. Otherwise, the cmap and `GSUB` resources supplied by Adobe are used.

From the Adobe CMap and CIDFont Files Specification, Version1.0: ‘Both the CIDFont and the CMap must use CIDs from compatible character collections. The identification of the character collection is accomplished by placing version control information into each CIDFont and CMap file. To identify a character collection uniquely, three name components are concatenated with a hyphen:

-  a registry name is used to identify an issuer of orderings, usually Adobe;

-  an ordering name is used to identify an ordered character collection; and,

-  a supplement number is used to indicate that the ordered character collection for a registry, ordering, and previous supplement has been changed to add new characters assigned CIDs beginning with the next available CID.

These three pieces of information taken together uniquely identify a character collection. In a CIDFont, this information declares what the character collection is. In a CMap, this information specifies which character collection is required for compatibility. A CMap is compatible with a CIDFont if the registry and ordering are the same. If the supplement numbers are different, some codes may map to the CID index of 0.’

sampleTexts

    Sample text. Corresponds to the OpenType `name` table ID 19. “This can be the font name, or any other text that the designer thinks is the best sample to display the font in.” This sample text is displayed, for instance, by Apple Font Book, when the font is selected in Sample view.

Save as TrueType

  boolean  Exports the instance as TTF, regardless of the settings in the Export dialog.

SBIX to SVG

  integer  If set, exports the bitmaps built for an `sbix` font in an `SVG` color table. The `SVG` table supports both bitmap and vector images, and with this parameter you can duplicate the `sbix` bitmap information into an equivalent `SVG` bitmap table, making the font more compatible. Adding the `Export sbix` parameter with a deactivated checkbox will export `SVG` only and not include `sbix` in the instance in question.

Scale to UPM

  integer  Scales the whole font to the supplied integer value. This is useful for scaling to a UPM of 2048 (or a power of two between 16 and 16,384) for TTF export, or if you are designing in an UPM size other than the default 1000.

shoulderHeight

  integer  A vertical metric value for Middle Eastern, South Asian and Southeast Asian scripts. In glyphs of those scripts, the shoulder height will be displayed as a vertical metric line in Edit view instead of the x-height. The algorithm for automatic creation of alignment zones also respects this value.

smallCapHeight

  integer  A vertical metric for small caps. The algorithm for automatic creation of alignment zones respects this value. When a small cap glyph is displayed in Edit view and metrics are set to show, the small cap height will be displayed instead of the x-height.

strikeoutPosition

  integer  “The position of the top of the strikeout stroke relative to the baseline in font design units”.Corresponds to the `yStrikeoutPosition` field in the `OS/2` table. “Positive values represent distances above the baseline; negative values represent distances below the baseline. Aligning the strikeout position with the em dash is suggested. Note, however, that the strikeout position should not interfere with the recognition of standard characters, and therefore should not line up with crossbars in the font.”

strikeoutSize

  integer  The size of the strike-out dash in units. Corresponds to the yStrikeoutSize field in the `OS/2` table. “This field should normally be the thickness of the em dash for the current font, and should also match the underline thickness.”

Style Name as STAT entry

  string  For variable fonts, takes the instance style name as combinable display string for an axis range. As value, use the four-letter axis tag to which the display string applies. Use this only in instances that are non-normal on one axis and normal on all others. That is because the normal attributes have elidable names and do not appear in the style name (e.g., “Semibold” or “Condensed”).

Example: In the Light instance, use this parameter with the value `wght`, because Light is a value on the weight axis. The Light instance is non-normal on the `wght` axis, but normal (i.e., not condensed nor extended) on the `wdth` axis.

styleMapFamilyNames

    Family name used for RIBBI style mapping (regular, italic, bold, bold italic). You can use this to create subfamilies within larger font families. “Up to four fonts can share the Font Family name, forming a font style linking group.” Glyphs uses the entries in Style Name field and in the Style Linking section in the Instances tab of the Font Info for linking the four individual weights.

styleMapStyleNames

    Localised Font Subfamily name. Corresponds to the OpenType `name` table ID 2

styleNames

    Style Name or Font Subfamily Name. Corresponds to OpenType `name` table ID 2.

“The Font Subfamily name is used in combination with Font Family name (name ID 1), and distinguishes the fonts in a group with the same Font Family name. This should be used for style and weight variants only.”

subscriptXOffset

  integer  The horizontal offset for simulated subscript typesetting, recommended to keep at zero for fonts with an italic angle of zero. Corresponds to the `subscriptXOffset` field in the `OS/2` table.

“The Subscript X Offset parameter specifies a font designer’s recommended horizontal offset – from the glyph origin to the glyph origin of the subscript’s glyph – for subscript glyphs associated with this font. If a font does not include all of the required subscript glyphs for an application, and the application can substitute glyphs, this parameter specifies the recommended horizontal position from the glyph escapement point of the last glyph before the first subscript glyph. For upright glyphs, this value is usually zero; however, if the glyphs of a font have an incline (italic or slant), the reference point for subscript glyphs is usually adjusted to compensate for the angle of incline.”

subscriptXSize

  integer  The horizontal scale for simulated subscript typesetting. Corresponds to the `subscriptXSize` field in the `OS/2` table.

“If a font has two recommended sizes for subscripts, e.g., numerics and other, the numeric sizes should be stressed. This size field maps to the em size of the font being used for a subscript. The horizontal font size specifies a font designer’s recommended horizontal size of subscript glyphs associated with this font. If a font does not include all of the required subscript glyphs for an application, and the application can substitute glyphs by scaling the glyphs of a font or by substituting glyphs from another font, this parameter specifies the recommended nominal width for those subscript glyphs. For example, if the em for a font is 2048 units and ySubScriptXSize is set to 205, then the horizontal size for a simulated subscript glyph would be 1/10th the size of the normal glyph.”

subscriptYOffset

  integer  The vertical offset for simulated subscript typesetting, typically a positive number for going below the baseline. Corresponds to the `subscriptYOffset` field in the `OS/2` table.

“The Subscript Y Offset parameter specifies a font designer’s recommended vertical offset from the glyph baseline to the glyph baseline for subscript glyphs associated with this font. Values are expressed as a positive offset below the glyph baseline. If a font does not include all of the required subscript glyphs for an application, this parameter specifies the recommended vertical distance below the glyph baseline for those subscript glyphs.”

subscriptYSize

  integer  The vertical scale for simulated subscript typesetting. Corresponds to the `subscriptYSize` field in the `OS/2` table. See subscriptXSize for more details.

superscriptXOffset

  integer  The horizontal offset for simulated superscript typesetting, recommended to keep at zero for fonts with an italic angle of zero. Corresponds to the `superscriptXOffset` field in the `OS/2` table. See subscriptXOffset for more details.

superscriptXSize

  integer  The horizontal scale for simulated superscript typesetting. Corresponds to the `superscriptXSize` field in the `OS/2` table. See subscriptXSize for more details.

superscriptYOffset

  integer  The vertical offset for simulated superscript typesetting, typically a positive value for going below the baseline. Corresponds to the `superscriptYOffset` field in the `OS/2` table. See subscriptYOffset for more details.

superscriptYSize

  integer  The vertical scale for simulated superscript typesetting. Corresponds to the `superscriptYSize` field in the `OS/2` table. See subscriptYSize for more details.

trademarks

    Trademark statement. Corresponds to the OpenType `name` table ID 7. According to Microsoft, “this is used to save any trademark notice / information for this font. Such information should be based on legal advice. This is distinctly separate from the copyright.”

TrueType Curve Error

  float  Maximum deviance of the approximated TrueType curve in units. Default is 0.6. A higher curve error allows the TrueType converter to use fewer quadratic splines to approximate the cubic splines of your design. This can result in a significantly smaller `glyf` table (containing the quadratic outline data), and smaller overall file size.

TrueType Keep GlyphOrder

  boolean  Keeps the glyph order as it is in the .glyphs file, except `.notdef` and `space` which always have to be in the first two positions. If disabled (the default), the font will resort the first four glyphs to: `.notdef`, `NULL`, `CR`, `space`. While `NULL` and `CR` will only be reordered if they exist in the .glyphs file, `.notdef` and `space` will be automatically generated if they are missing. **Use this parameter only if you know what you are doing.**

TTFAutohint binary path

  string  File path to a precompiled TTFAutohint binary that should be used instead of the built-in TTFAutohint. This can be useful if you need to stick to a specific version or want to employ a newer version of TTFAutohint than Glyphs incorporates.

TTFAutohint control instructions

  string  This allows you to specify TTFAutohint control instructions. It is recommended to prepare the control code in a separate file and then paste it into the value of the parameter. Possible instructions are:

-  `glyphnames left pointIDs offset`

-  `glyphnames right pointIDs offset`

-  `glyphnames nodir pointIDs`

-  `glyphnames touch pointIDs xshift x yshift y @ PPMs`

-  `glyphnames point pointIDs xshift x yshift y @ PPMs`

Values for `offset` are optional and assumed as zero when omitted. In the `touch` and `point` instructions, either or both of the shifts can be specified. `x` and `y` must be between 0.0 and 1.0. `glyphnames` can be one or more comma-separated glyph names, specified as production names (i.e., the names as they are written into the font file). `PPMs` can be a single PPM size, a size range of PPMs with a hyphen, or a comma-separated list of sizes and size ranges. A line that starts with a hashtag `#` is considered a comment and therefore ignored. The instructions can be abbreviated with their respective first letters, e.g., “right” can be written as “r”.

TTFAutohint options

  string  Specifies commandline options for the TrueType autohinter “ttfautohint”. Use the dialog sheet to configure your settings:

-  _Hint Set Range:_ the PPM range for which the instructions will be optimized. Large ranges can cause huge file sizes.

-  _Default Script:_ “default script for OpenType features”.

-  _Fallback Script:_ “default script for glyphs that can’t be mapped to a script automatically”.

-  _Hinting Limit:_ the PPM size “where hinting gets switched off”.  Default is 200 pixels, must be larger than the maximum of the hint set range. Pixel sizes up to this size use the hinting configuration for the range maximum.

-  _Fallback Stem Width:_ “the horizontal stem width (hinting) value for all scripts that lack proper standard characters in the font. The value is given in font units and must be a positive integer. If not set, ttfautohint uses a hard-coded default (50 units at 2048 units per em, and linearly scaled for other UPM values, for example 24 units at 1000 UPM).” For symbol fonts, you also need to specify a Fallback Script “to set up a script at all”.

-  _x-Height Increase Limit:_ from this pixel size down to 6 PPM, the x-height is more likely to be rounded up. Default is 14 PPM. “Normally, ttfautohint rounds the x height to the pixel grid, with a slight preference for rounding up. (…) Use this flag to increase the legibility of small sizes if necessary.” Set to 0 if you want to switch off rounding up the x-height.

-  _x-Height Snapping Exceptions:_ “list of comma-separated PPM values or value ranges at which no x-height snapping shall be applied”, e.g., “8, 10-13, 16” disables x-height snapping for sizes 8, 10, 11, 12, 13, and 16. An empty string means no exceptions, and a mere dash (“-”) disables snapping for all sizes.

-  _Adjust Subglyphs (formerly known as Pre-Hinting):_ If enabled, “makes a font’s original bytecode be applied to all glyphs before it is replaced with bytecode created by ttfautohint. This makes only sense if your font already has some hints in it that modify the shape even at EM size (normally 2048px); in particular, some CJK fonts need this because the bytecode is used to scale and shift subglyphs (hence the option’s long name). For most fonts, however, this is not the case.”

-  _Dehint:_ Disables all TT hinting, and therefore overrides all other options. Use only for testing.

-  _Detailed Info:_ if enabled, adds “ttfautohint version and command line information to the version string or strings (with name ID 5) in the font’s `name` table”. This option is mutually exclusive with the _No Autohint Info_ option (see below). “If neither is set, the string “ttfautohint (vNNN)” gets added to the `name` table”, NNN being the ttfAutohint version.

-  _Hint Composites:_ “By default, the components of a composite glyph get hinted separately. If this flag is set, the composite glyph itself gets hinted (and the hints of the components are ignored). Using this flag increases the bytecode size a lot, however, it might yield better hinting results – usually, it doesn’t.” Also adds a ghost component called .ttfautohint to all glyphs. “Direct rendering of the .ttfautohint subglyph (this is, rendering as a stand-alone glyph) disables proper hinting of all glyphs in the font! Under normal circumstances this never happens because .ttfautohint doesn’t have an entry in the font’s `cmap` table.” But it can happen, e.g., in a glyph overview.

-  _Ignore Restrictions:_ “By default, fonts that have bit 1 set in the fsType field of the `OS/2` table are rejected. If you have a permission of the font’s legal owner to modify the font, specify this command line option.”

-  _No Autohint Info:_ if checked, prevents adding “ttfautohint version and command line information to the version string or strings (with name ID 5) in the font’s `name` table.”

-  _Symbol Font:_ “Process a font that ttfautohint would refuse otherwise because it can’t find a single standard character for any of the supported scripts. For all scripts that lack proper standard characters, ttfautohint uses a default (hinting) value for the standard stem width instead of deriving it from a script’s set of standard characters (for the latin script, one of them is character “o”). Use this option – usually in combination with the Fallback Script and/or Fallback Stem Width option – to hint symbol or dingbat fonts or math glyphs, for example.”

-  _ttfa table:_ Adds an OpenType table “called `TTFA` to the output font that holds a dump of all parameters. In particular, it lists all ttfautohint control instructions (which are not shown in the name table info). This option is mainly for archival purposes so that all information used to create a font is stored in the font itself. Note that such a `TTFA` table gets ignored by all TrueType rendering engines. Forthcoming versions of the ttfautohint front-ends will be able to use this data so that a font can be processed another time with exactly the same parameters, thus providing a means for round-tripping fonts.”

-  _Windows Compatibility:_ “This option makes ttfAutohint add two artificial blue zones, positioned at the `winAscent` and `winDescent` values (from the font’s `OS/2` table). The idea is to help ttfAutohint so that the hinted glyphs stay within this horizontal stripe since Windows clips everything falling outside.” Use this option if clipping occurs in Microsoft Windows and you cannot adjust `winAscent` and `winDescent` instead (which would usually be the better option). In combination with “-” as value for xHeight Snapping Exceptions (see above), it should both “suppress any vertical enlargement” and “prevent almost all clipping.”

-  _Strong Stems:_ specifies which algorithm to use “for computing horizontal stem widths and the positioning of blue zones” for the three rendering targets: Grayscale (Android), GDI ClearType (old Windows versions including XP), DW ClearType (IE 9 and later, and Windows 7 and later). If disabled, stems will be quantized: “Both stem widths and blue zone positions are slightly quantized to take discrete values. For example, stem values 50, 51, 72, 76, and 100 would become 50, 74, and 100 (or something similar). More glyph shape distortion but increased contrast.” If enabled, stems will be strong: “Stem widths and blue zones are snapped and positioned to integer pixel values as much as possible. This gives high contrast, but glyph shape distortion can be significant.”

TTFBlueFuzz

  integer  Much like PostScript’s BlueFuzz, extends the range of TrueType alignment zones by the given amount in both directions. Default and fallback value is 1. Only affects zones defined in the TTFZones parameter.

TTFDontPreserveDiagonals

  boolean  In manual TT hinting, the apparent angles of slanted stems are preserved, even when another stem crosses it and threatens to make it appear broken. E.g. in an uppercase A, the two diagonal stems are preserved in their angles, even though a (hinted) crossbar interrupts the outline in their middles. With this parameter, stem angles are _not_ preserved. Technically, the parameter suppresses (projections onto) freedom vectors. Useful for making TT hinting smaller, e.g., for webfont export.

TTFFamilyZonesThreshold

  integer  The PPM size until which Family Alignment Zones are applied. For adding family alignment zones, add a TTFZones parameter to “Font Info” → “Font” rather than “Font Info” → “Master” and make sure the number of defined zones is the same in both places.

TTFMinimumDistance

  float  Any hinted stem will be drawn with this minimum length in pixels, no matter which PPM size, if it has a stem hint applied to it. The default is 0.25. This value can be important in small pixel sizes, where small parts are in danger of disappearing.

TTFOvershootSuppressionBelowPPM

  integer  The pixel size (PPM) up to which overshoots are reliably flattened out. Only applies to manual TT hinting, not ttfAutohint.

TTFStems

  list  A list of stem definitions for TrueType manual hinting only. When you click in the parameter value, a dialog sheet will drop down. Use the gear menu to add or remove stem definitions, or import the currently available horizontal PostScript stems from the Horizontal Stems and Vertical Stems fields in “File” → “Font Info” → “Masters.” For each stem, you can define an orientation, a name and a width. In the main master, a delta and a globe symbol will be shown in addition: they provide access to dialogs for defining PPM deltas as well as a glyph filter for the stem in question. Add stems by pressing on the plus button, and remove a stem by selecting it and clicking the minus button.

-  _Orientation:_ Switch between horizontal stem (e.g., for the crossbars in e, f, t, or the top and bottom curves of o, c, e, a)  and vertical stem (e.g., for the vertical stems of h, m, n, u, or the left and right curves of o)  by clicking on the double arrow symbol.

-  _Name:_ The stem name is arbitrary, but should be unique. Will show up in the pop-up menu in the grey info box when the TT Instructor tool (I) is active and a stem hint (S) is selected.

-  _Width:_ The average size of the stem towards which the stems will be rounded. Also, when applying the Autohint command from the context menu of the TT Instructor tool (I),  stems will be identified with this size.

-  _Deltas:_ PPM-specific size adjustments for the effective pixel-size of a stem in an instance. In any PPM/instance field, click repeatedly to switch between no change (blank field), size increase (arrow up), size decrease (arrow down). The deltas are only accessible in the first master, or the master defined in the Get Hints From Master parameter.

-  _Filter (Scope):_ Define the glyph scope of the stem by adding logical filters. Click on the plus button to add additional filters, and the minus button to remove a selected filter. Opt-click on the plus button to add logical AND and OR operators for the following (indented) conditions. Available filters are Name, Category, Subcategory and Script. TrueType stems with a scope will only be available in glyphs that fulfill the logical conditions of its scope. Scopes are only accessible in the first master, or the master defined in the Get Hints From Master parameter.

TTFZoneRoundingThreshold

  float  Controls the likelihood of a positive zone being pushed up a pixel. It takes a small decimal number as value, typically something around 0.1 or 0.2. The value is added to any positive zone position before rounding, and added twice to the x-height zone (the one named “xHeight” in the TTFZones parameter). Default is 0.09375.

Example: At a certain font size, the smallcap zone ends up at 6.45 pixels, and the x-height at 5.25 pixels. Without any change, the smallcap zone would round and snap to a height of 6 pixels, while the x-height would end up with 5 pixels. If you set a value of 0.2, the smallcap height ends up at (6.45+0.2=6.65≈) 7 pixels, and the x-height at (5.25+2×0.2=5.65≈) 6 pixels.

TTFZones

  list  A list of zone definitions for horizontal TrueType stems, in manual TrueType hinting only. When you click in the parameter value, a dialog sheet will drop down. Use the gear menu to add or remove zone definitions, or import the currently available PostScript zones from Alignment Zones field in “File” → “Font Info” → “Masters.” For each zone, you can define a name, a position, a size and an alignment. In the main master, a delta and a globe symbol will be shown in addition: they provide access to dialogs for defining PPM deltas as well as a glyph filter for the zone in question. Add zones by pressing on the plus button, and remove a zone by selecting it and clicking the minus button.

-  _Name:_ The zone name is arbitrary, but should be unique. Will show up in the pop-up menu in the grey info box when the TT Instructor tool (I) is active and an align hint (A) is selected.

-  _Position:_ Position of the zone, or “flat end” of overshooting shapes, similar to alignment zones in PostScript.

-  _Size:_ Size of the zone, or distance from “flat end” to the outermost edge of overshooting shapes. Use positive values for top zones, negative values for bottom zones. If the zone size is calculated to be less than half a pixel in any given PPM size, any hinted shape that reaches into the zone will be flattened to the same height.

-  _Align:_ Link a zone to another zone with the Align option. If a zone is aligned to another, the distance between the zone positions is rounded and applied to the zone. This will result in more consistent transitions when you step your font through pixel sizes. Use this for heights that are very close to each other, perhaps even overlapping, and may appear next to each other in typesetting, and where it may be perceived as problematic if the heights diverge too far in low-res pixel renderings, e.g., align the small-cap height to the x-height. Aligned zones will be displayed at the same height if the difference is less than half a pixel in a given PPM size; and at least one pixel apart if the difference is half a pixel or more.

-  _Delta:_ PPM-specific position rounding for the effective pixel-size of each zone in each instance. In any PPM/instance field, click repeatedly to switch between no change (blank field), shifting up (arrow up), shifting down (arrow down). The deltas are only accessible in the first master, or the master defined in the Get Hints From Master parameter.

-  _Filter (Scope):_ Define the glyph scope of the stem by adding logical filters. Click on the plus button to add additional filters, and the minus button to remove a selected filter. Opt-click on the plus button to add logical AND and OR operators for the following (indented) conditions. Available filters are Name, Category, Subcategory and Script. TrueType stems with a scope will only be available in glyphs that fulfill the logical conditions of its scope. Scopes are only accessible in the first master, or the master defined in the Get Hints From Master parameter.

typoAscender

  integer  The height of the ascenders in units. Corresponds to the OpenType `OS/2` table `sTypoAscender` field.

`The typographic ascender for this font. This field should be combined with the `typoDescender` and `typoLineGap` values to determine default line spacing. This field is similar to the `hheaAscender` field as well as to the `winAscent` field. However, legacy platform implementations used those fields with platform-specific behaviors. As a result, those fields are constrained by backward-compatibility requirements, and they do not ensure consistent layout across implementations. The `typoAscender`, `typoDescender` and `typoLineGap` fields are intended to allow applications to lay out documents in a typographically-correct and portable fashion. The `Use Typo Metrics` flag (`fsSelection` bit 7) is used to choose between using sTypo* values or usWin* values for default line metrics. It is _not_ a general requirement that `typoAscender` - `typoDescender` be equal to unitsPerEm. These values should be set to provide default line spacing appropriate for the primary languages the font is designed to support.

For CJK (Chinese, Japanese, and Korean) fonts that are intended to be used for vertical (as well as horizontal) layout, the required value for `typoAscender` is that which describes the top of the ideographic em-box. For example, if the ideographic em-box of the font extends from coordinates 0,-120 to 1000,880 (that is, a 1000 × 1000 box set 120 design units below the Latin baseline), then the value of `typoAscender` must be set to 880. Failing to adhere to these requirements will result in incorrect vertical layout.

For a detailed discussion of vertical metrics, see the Vertical Metrics tutorial.

typoDescender

  integer  A _negative_ integer describing the depth of the descenders in units. Corresponds to the `sTypoDescender` field of the OpenType `OS/2` table.

“The typographic descender for this font. This field should be combined with the `typoAscender` and `typoLineGap` values to determine default line spacing.” See `typoAscender` for more details.

typoLineGap

  integer  The recommended whitespace between lines, measured in units. Corresponds to the OpenType `OS/2` table `sTypoLineGap` field.

“The typographic line gap for this font. This field should be combined with the `typoAscender` and `typoDescender` values to determine default line spacing.” See `typoAscender` for more details.

underlinePosition

  integer  The suggested distance from the baseline to the top of the underline. Negative values indicate a position below the baseline. Corresponds to the `post` table entry `underlinePosition`. Default is −100.

underlineThickness

  integer  Underline thickness value. Corresponds to the `post` table entry `underlineThickness`. Default is 50. “In general, the underline thickness should match the thickness of the underscore character (U+005F), and should also match the strikeout thickness, which is specified in the `OS/2` table.”

unicodeRanges

  list  A list of supported Unicode ranges in the font. Corresponds to the OpenType `OS/2` table `ulUnicodeRange1`, `ulUnicodeRange2`, `ulUnicodeRange3` and `ulUnicodeRange4` fields. The dialog offers a search field, so you can quickly spot the proper ranges for your fonts. E.g., if you want to cover all Latin ranges, simply search for “latin” and all corresponding ranges in the list will be displayed.

“If a bit is set, then the Unicode ranges assigned to that bit are considered functional. If the bit is clear, then the range is not considered functional. Each of the bits is treated as an independent flag and the bits can be set in any combination. The determination of “functional” is left up to the font designer, although character set selection should attempt to be functional by ranges if at all possible.”

uniqueID

  string  Unique font identifier. Corresponds to the OpenType `name` table ID 3

unitsPerEm

  integer  Units per em. Default is 1000 for PostScript-flavored OpenType fonts and a power of two between 16 and 16,384 (usually 2048) for TrueType-flavored OpenType fonts. The value specified is the amount of units that will be used for the font size. A smaller value will cause the font to appear larger on screen, and vice versa. This parameter will only set the UPM value, and not scale node coordinates and other measurements. If you do want to scale, see Scale to UPM.

Update Features

  boolean  Forces an update of all automatic feature code. This is especially useful in a phase of font production where the glyph set changes a lot, or, if explicitly turned off, for suppressing the automatic feature code generation.

Use Arabic Presentation Form Unicodes

  boolean  Use legacy Presentation Form Unicode values for Arabic glyphs

Use Extension Kerning

  boolean  If checked, additional kern lookups will be created with a `GPOS` Extension lookup type (a.k.a. lookup type 9), allowing the font to store more kerning values. Use this when the attempt to export your font results in an offset overflow error in the `GPOS` table, and you cannot or do not want to delete kern pairs, especially exceptions.

“This lookup provides a mechanism whereby any other lookup type’s subtables are stored at a 32-bit offset location in the `GPOS` table. This is needed if the total size of the subtables exceeds the 16-bit limits of the various other offsets in the `GPOS` table. In this specification, the subtable stored at the 32-bit offset location is termed the “extension” subtable.”

Use Line Breaks

  boolean  If checked, line breaks inside OpenType features will not be escaped (i.e., not replaced with `\012`) when stored in a .glyphs file. If unchecked, can facilitate version control, and thus makes sense, e.g., in a git-based workflow.

Use Typo Metrics

  boolean  If checked, applications that respect this setting (in particular, versions of Microsoft Office since 2006) will prefer `typoAscender`, `typoDescender`, and `typoLineGap` over `winAscent` and `winDescent` for determining the vertical positioning. Default is off. Corresponds to bit 7 (“don’t use Win line metrics”) in the `OS/2` table `fsSelection` field. According to Adobe’s MakeOTF User Guide, this bit was introduced “so that reflow of documents will happen less often than if Microsoft just changed the behavior for all fonts.”

Microsoft: “If set, it is strongly recommended that applications use typoAscender − typoDescender + typoLineGap as the default line spacing for this font.”

“In variable fonts, default line metrics should always be set using the `typoAscender`, `typoDescender` and `typoLineGap` values, and the Use Typo Metrics flag should be set. The ascender, descender and lineGap fields in the hhea table should be set to the same values as `typoAscender`, `typoDescender` and `typoLineGap`. The `winAscent` and `winDescent` fields should be used to specify a recommended clipping rectangle.”

Variable Font Family Name

  string  Family name for the variable font export. It makes sense to have a different family name for the likely use case that both static and variable fonts are in use at the same time.

Variable Font File Name

  string  File name for the variable font export. Overrides the default “VF.ttf” ending that Glyphs employs.

Variable Font Optimize Deltas

  boolean  Will drop OpenType Variation deltas from a contour if none of its nodes moves more than half a unit. Default is on. Set this parameter to off in order to also keep low-significant deltas.

Variable Font Origin

  string  Master to be used for the set of outlines that will be stored in the variable font file. All other masters and instances will be reached by adding point deltas to these default outlines.

Variable Font Style Name

  string  Family name for the variable font export. It makes sense to have a different family name for the likely use case that both static and variable fonts are in use at the same time.

Variable SubfamilyName

  string  Style name for the variable font’s origin master, the (default) outlines stored in the exported variable font.

variablePostscriptFontName

    PostScript name of the variable font instance. Corresponds to the OpenType `name` table ID 6 and the postscriptName for NamedInstance entries in the OpenType `fvar` table. Should be ASCII-only, and no whitespace allowed, e.g., “MyFontVar-BoldCondensedItalic”. Do not confuse with postscriptFullName.

“The FontName generally consists of a family name (specifically, the one used for FamilyName), followed by a hyphen and style attributes in the same order as in the FullName.”

Must be distinct from the static PostScript Font Name, or may cause a font conflict if both the static and variable font are installed by a user. It is recommended that it be Variations PostScript Name Prefix (ID 25), followed by a hyphen, followed by the style name (ASCII, no spaces).OpenType spec: name ID 6

variableStyleName

  string  Family name for the variable font export. It makes sense to have a different family name for the likely use case that both static and variable fonts are in use at the same time.

variableStyleNames

    Style name used for variable fonts.

This can be useful when (static) instance names are reused with different static family names (e.g., “Bold” in “Myfamily Condensed” and “Bold” in “Myfamily”), which would otherwise cause duplicate entries in the `fvar` table.

Variation Font Origin

  string  Master to be used for the set of outlines that will be stored in the variable font file. All other masters and instances will be reached by adding point deltas to these default outlines.

variationsPostScriptNamePrefix

  string  PostScript Name Prefix for Variable Fonts. Corresponds to name ID 25 in the OpenType `name` table. For processing of a variable font instance, e.g., in a PDF, a specific PostScript name is calculated automatically, based on the PostScript Font Name, axis tags, and axis positions (design space coordinates). This constructed PostScript name cannot be longer than 127 characters. If no prefix is provided, the US English string for typographic (“preferred”) family name (name ID 16) will be used, minus any characters not within ASCII A-Z, a-z and 0-9.

Microsoft: used as “family prefix in the PostScript Name Generation for Variation Fonts algorithm. The character set is restricted to ASCII-range uppercase Latin letters, lowercase Latin letters, and digits. All name strings for name ID 25 within a font, when converted to ASCII, must be identical.”

Adobe: ‘Including a Variable PostScript Name Prefix string (name ID 25) in a font could be useful in the following cases:

-  if the US English typographic family name, US English named instance fvar subfamilyNameID, or the number of axis descriptors in the font could tip the length of the generated PostScript names to over 127 characters, or

-  if the US English typographic family name contains accented or other characters that when removed by the algorithm ... could cause confusion or even ambiguity in PostScript names. For example, both typographic family names “André Sans” and “Andró Sans” resolve to family prefix “AndrSans”, an ambiguity that could be avoided by providing Variation PostScript Name Prefixes “AndreSans” and “AndroSans” in the fonts.’

vendorID

  string  Four-character identifier for the creator of the font, consisting of printable ASCII characters (U+0020 through U+007E) only. Corresponds to the achVendID field in the OpenType `OS/2` table. If not set, Glyphs will use “UKWN” (“unknown”) as Vendor ID. ‘This is not the royalty owner of the original artwork. This is the company responsible for the marketing and distribution of the typeface that is being classified. For example, there may be multiple vendors of ITC Zapf Dingbats, with some vendors providing differentiating benefits in their fonts (more kern pairs, unregularized data, hand hinted, etc.). This identifier will allow for the correct vendor’s type to be used over another, possibly inferior, font file.

Microsoft maintains a registry of vendor IDs. Registered IDs must be unique to a single vendor. Non-registered IDs can also be used, but are discouraged: vendors are strongly encouraged to register an ID to ensure that there are no conflicts between different vendors in use of a given ID, and that customers are able to find vendor contact information for a given font. This field can also be left blank (set to null, or a tag comprised of four space characters).’

versionString

  string  Version string. Should begin with the syntax “Version .” (with a space between “Version” and the number). A placeholder string into which the version number will be inserted automatically, e.g., `Version %d.%03d`, where %d stands for an integer, and %03d for integer represented with three digits, e.g., `008`. The string must contain a version number of the following form: one or more digits (0-9) of value less than 65,535, followed by a period, followed by one or more digits of value less than 65,535. Any character other than a digit will terminate the minor number. A character such as “;” is helpful to separate different pieces of version information. The first such match in the string can be used by installation software to compare font versions. Note that some installers may require the string to start with “Version ”, followed by a version number as above.

vheaVertAscender

  integer  Ascender value for vertical typesetting. Corresponds to the `vertTypoAscender` field in the OpenType `vhea` table.

“The vertical typographic ascender for this font. It is the distance in units from the ideographic em-box center baseline for the vertical axis to the right edge of the ideographic em-box. It is usually set to UPM ÷ 2. For example, a font with an em of 1000 units will set this field to 500.”

vheaVertDescender

  integer  Descender value for vertical typesetting, typically a negative number. Corresponds to the `vertTypoDescender` field in the OpenType `vhea` table.

“The vertical typographic descender for this font. It is the distance in units from the ideographic em-box center baseline for the vertical axis to the left edge of the ideographic em-box. It is usually set to −UPM ÷ 2. For example, a font with an em of 1000 units will set this field to −500.”

vheaVertLineGap

  integer  Line gap value for vertical typesetting. Corresponds to the `vertTypoLineGap` field in the OpenType `vhea` table.

“The vertical typographic gap for this font. An application can determine the recommended line spacing for single spaced vertical text for an OpenType font by the following expression: ideographic embox width + vertTypoLineGap.”

Virtual Master

    Defines a font master for a variable font, thereby extending its design space accordingly. Rather than a “real” master, which is defined in “File” → “Font Info” → “Masters,” a virtual master can only be drawn in the form of a Brace layer, i.e., a glyph layer with a name consisting of or ending in the comma-separated design space coordinates between curly braces, e.g., “{100, 300}”. A virtual master makes most sense for design axes that only apply to a limited number of glyphs, e.g., an axis that controls the middle crossbar heights of letters like A, E, F and H. The main advantages are that only affected glyphs need to be managed, and kerning does not need to be redone for an extra “real” master.

Webfont Formats

  list  For the instance in which this parameter is specified, the listed webfont formats will be exported, regardless of the settings in the Export dialog. Possible values: TTF, EOT, WOFF or WOFF2.

Webfont Only

  boolean  If activated, it removes some of the information stored in the font file necessary for desktop use. This makes it harder to convert the webfont into a different format or to install it locally in an operating system like Windows or macOS. Careful: Technically, this option produces a damaged font, which, however, still works as webfont in browsers.

winAscent

  integer  A positive integer describing the top extremum of the font rendering box for Windows, beyond which glyph renderings may be clipped. Thus, `winAscent` should be high enough to include all parts of all important glyphs. Corresponds to the usWinAscent field in the OpenType `OS/2` table.

“The “Windows ascender” metric. This should be used to specify the height above the baseline for a clipping region. This is similar to the `typoAscender` field, and also to the `hheaAscender` field. There are important differences between these, however. In the Windows GDI implementation, the `winAscent` and `winDescent` values have been used to determine the size of the bitmap surface in the TrueType rasterizer. Windows GDI will clip any portion of a TrueType glyph outline that appears above the `winAscent` value. If any clipping is unacceptable, then the value should be set greater than or equal to yMax. _Note:_ This pertains to the default position of glyphs, not their final position in layout after data from the `GPOS` or `kern` table has been applied. Some legacy applications use the `winAscent` and `winDescent` values to determine default line spacing. This is strongly discouraged. The `typoAscender`, `typoDescender` and `typoLineGap` fields should be used for this purpose. Note that some applications use either the `winAscent `/`winDescent` values or the `typoAscender`/`typoDescender`/`typoLineGap` values to determine default line spacing, depending on whether the `Use Typo Metrics` flag is set. This may be useful to provide compatibility with legacy documents using older fonts, while also providing better and more-portable layout using newer fonts. Applications that use the `typoAscender`/`typoDescender`/`typoLineGap` fields for default line spacing can use the `winAscent`/`winDescent` values to determine the size of a clipping region. Some applications use a clipping region for editing scenarios to determine what portion of the display surface to re-draw when text is edited, or how large a selection rectangle to draw when text is selected. Early versions of this specification suggested that the `winAscent` value be computed as the yMax for all characters in the Windows ANSI character set. For new fonts, the value should be determined based on the primary languages the font is designed to support, and should take into consideration additional height that may be required to accommodate tall glyphs or mark positioning.”

For a detailed discussion of vertical metrics, see the Vertical Metrics tutorial.

winDescent

  integer  A _positive_ integer describing the bottom extremum of the font rendering box for Windows. Thus, `winDescent` should be large enough to encompass the descenders of lowercase letters like g, p, q, and y. Corresponds to the `usWinDescent` field of the OpenType `OS/2` table.

“Early versions of this specification suggested that the `winDescent` value be computed as -yMin for all characters in the Windows ANSI character set. For new fonts, the value should be determined based on the primary languages the font is designed to support, and should take into consideration additional vertical extent that may be required to accommodate glyphs with low descenders or mark positioning.”

Write DisplayStrings

  boolean  If disabled, prevents the _DisplayStrings_ from being written into the .glyphs file. _DisplayStrings_ store the text content of Edit tabs. This can facilitate version control. Default is enabled.

Write lastChange

  boolean  If disabled, prevents the _Last Changed Date_ from being written into the .glyphs file. This can facilitate version control. Default is enabled.

WWSFamilyName

  string  WWS family name. WWS stands for “Weight Width Slope”. Corresponds to the OpenType `name` table ID 21.

“Used to provide a WWS-conformant family name in case the entries for IDs 16 (preferredFamilyName) and 17 (preferredSubfamilyName) do not conform to the WWS model. (That is, in case the entry for ID 17 includes qualifiers for some attribute other than weight, width or slope.)” Frequent use cases are family names that indicate optical sizes: “Examples of name ID 21: “Minion Pro Caption” and “Minion Pro Display”. (Name ID 16 would be “Minion Pro” for these examples.)”

WWSSubfamilyName

  string  WWS Subfamily name. Corresponds to the OpenType `name` table ID 22.

“Used in conjunction with ID 21, this ID provides a WWS-conformant subfamily name (reflecting only weight, width and slope attributes) in case the entries for IDs 16 and 17 do not conform to the WWS model.[…] Examples of name ID 22: “Semibold Italic”, “Bold Condensed”. (Name ID 17 could be “Semibold Italic Caption”, or “Bold Condensed Display”, for example.)” For name IDs 16 and 17, see the entries for preferredFamilyName and preferredSubfamilyName, respectively.