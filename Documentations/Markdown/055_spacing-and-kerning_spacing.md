### Spacing

Spacing is the process of adjusting the sidebearings of glyphs to achieve an even rhythm in a line of text.
There are no fixed rules for how large or small the sidebearings of a glyph should be.
The amount of spacing depends on the style of the font and the script of the glyphs.
In general, glyphs that share similar shapes share similar sidebearing values.
For example, the left sidebearing of the Latin “K” is usually the same as the left sidebearing of the Latin “H”, while the right sidebearing of the Latin “D” and the Latin “O” should be the same or similar.

When the Text tool  is active and “View” → “Show Metrics” (Cmd-Shift-M) is checked, the sidebearing values and widths of all glyphs are displayed:

#### Info Box

The Info box (“View” → “Show Info”, Cmd-Shift-I) shows the sidebearings of  the current glyph.
In text mode, the current glyph is placed after the text cursor.
For left to right and right to left scripts, the sidebearing values are shown to the left and right of the  metrics icon in the center of the Info box:

For a top to bottom script, the Info box shows the top and bottom sidebearings next to the _{T} and _{B}:

Use the Up and Down arrow keys to increase and decrease a value in the Info box.
Hold down Shift for steps of 10 and both Shift and Command for steps of 100.

Editing sidebearings in the Info box can be handy for quick adjustments.
When editing the spacing of many glyphs, consider using the spacing shortcuts.

#### Spacing Shortcuts

Mnemonic:

the Control key is located on the left, and the Command key is on the right.
Control: left sidebearing.
Command: right sidebearing.

Spacing shortcuts can be used with the Text tool to change the sidebearings of the current glyph.
Hold down the Control key to change the left sidebearing (LSB) with the Left Arrow and Right Arrow keys (⌃⯇ and ⌃⯈).
Hold down the Command key to change the right sidebearing (RSB) with the Left Arrow and Right Arrow keys (⌘⯇ and ⌘⯈).
Hold down Shift for steps of 10.

| Shortcut | Action |
|---|
| Ctrl-Left |  increase spacing on left side  |
| Ctrl-Shift-Left |  increase spacing on left side by 10 units  |
| Ctrl-Right |  decrease spacing on left side  |
| Ctrl-Shift-Right |  decrease spacing on left side by 10 units  |
| Cmd-Right |  increase spacing on right side  |
| Cmd-Shift-Right |  increase spacing on right side by 10 units  |
| Cmd-Left |  decrease spacing on right side  |
| Cmd-Shift-Left |  decrease spacing on right side by 10 units  |

When both the Control and Command keys are held down, the LSB and RSB are changed simultaneously, shifting the glyph inside its width.
This is particularly useful in monospaced designs, where the width of the glyph cannot be changed.

| Shortcut | Action |
|---|
| Cmd-Ctrl-Left |  shift glyph outline left  |
| Cmd-Ctrl-Shift-Left |  shift glyph outline left by 10 units  |
| Cmd-Ctrl-Right |  shift glyph outline right  |
| Cmd-Ctrl-Shift-Right |  shift glyph outline right by 10 units |

The Control and arrow key shortcuts (⌃⯇ and ⌃⯈) conflict with the default system shortcuts for Mission Control.
If they do not work in Glyphs, disable or change them in “System Settings” → “Keyboard” → “Shortcuts” → “Mission Control”.

#### Metrics Keys

Metrics keys can be used instead of numeric metrics values to link the metrics—the LSB, RSB, and width—of one glyph to those of another.
Write the name of a glyph in a sidebearing or width field in the Info box to use the metric value of that glyph.
For example, the LSB of an h could be linked to the l and its RSB to the n:

Linked metrics are _not synced automatically_ when the metrics of the linked glyphs are changed.
Instead, in Edit View, out-of-sync metrics keys are displayed in red next to an update  button:

Sync a metric key by clicking its update  button.
Fix all out-of-sync metrics on the current layer by choosing “Glyph” → “Update Metrics” (Cmd-Ctrl-M).
Hold down the Option key to update the metrics on all masters (Cmd-Opt-Ctrl-M).
These commands also work when multiple glyphs are selected.

In Font View, out-of-sync metrics are indicated by a warning  triangle in the top-right corner of the glyph cells.
Consider using a Smart Filter to reveal all of the glyphs with out-of-sync metrics.

###### Metrics Key Calculations

The sidebearing fields can contain simple calculations following these rules: a calculation starts with an equal sign (“=”) and a glyph name, followed by a mathematical operator, `+` (plus, addition), `-` (minus, subtraction), `*` (asterisk, multiply), or `/` (forward slash, divide), and ends with a number.
For example, “=n+10” is the metric value of the n glyphs plus 10, and “=comma/2” indicates half the metric value of the comma glyph.
Decimal numbers can also be used: “=o*1.2” or “=koKai-thai/1.5”.
The result of a calculation is rounded to the nearest font unit.

###### Constant Metrics Keys

Equating with a number such as “=50” fixes a metric to that value.
This is helpful if the metric should keep its value even when the outlines are changed.
A calculation that only contains a glyph name (such as “=n”) has the same effect as writing just the glyph name (“n”).

###### Mirrored Metrics Keys

Place a pipe character (“|”) directly after the equals sign to reference the opposite sidebearing.
For example, writing “=|n” in the right sidebearing of the u uses the value of the left sidebearing of the n.
Keep a glyph centered by writing “=|” into one of its sidebearing fields.
Such a value will reflect the opposite sidebearing of the same glyph, thus centering the glyph outlines inside its bounding box.

###### Local Metrics Keys

By default, a metrics key applies to all masters of the font.
Prefix a metrics key with two equals signs (“==”) instead to specify a local metrics key.
Local metrics keys do not affect other masters and can be used as exceptions.
Examples: “==m” or “==hyphen+15”.

###### Metrics Keys at Baseline Offsets

Add an at-sign (“@”) and a number at the end of a metrics key to measure a sidebearing at a specific offset from the baseline.
For example, “=A@0” is the sidebearing of A on the baseline, and “=A@200” is the sidebearing value of A as measured 200 units above the baseline.

#### Metrics Keys & Automatic Alignment

The metrics fields in the Info box of an automatically aligned glyph show the text “auto” and the derived values in parentheses.
Modify an automatic metric while keeping it automatically aligned by entering an equals sign, a plus or minus sign, and the offset value that should be added or removed.
For example, “=+25” or “=-10”.

Modifying automatic metrics can be useful for glyphs where a mark reaches far outside the glyph box.
Typical examples are idieresis (“ï”), dcaron (“ď”), and lcaron (“ľ”).