### Previewing & Testing

#### Previewing Kerning

Kerning can be previewed with three modes: no kerning , kerning , and locked kerning .
See Kerning Modes for details.

#### Previewing Masters

The glyphs in Edit View are drawn for the currently selected master.
Change the current master by clicking the icon for the master in the toolbar.

Set master icons in “File” → “Font Info…” → “Masters”.
Switch to one of the first nine masters of the font by pressing Command and the number of the master: Cmd-1, Cmd-2, …, Cmd-9.
Change the master of the currently edited glyph or the selected glyphs in Edit View by selecting a master layer from the “Layers” palette.
For more details on working with multiple font masters, see Interpolation.

#### Previewing OpenType Features

Toggle OpenType features from the “Features” menu at the bottom-left of the window in Edit View.
When at least one feature is selected, the Features menu is highlighted in an accent color.
The button will show the four-letter tags of the active features.

Activate a feature by selecting it from the Features menu.
Multiple features may be active at the same time.
Select a feature from the menu again to deactivate it in Edit View.
Deactivate all features by choosing the dash (-) at the top of the menu.
Recompile the font features from the features editor (“File” → “Font Info…” → “Features”) to make newly added features appear in the menu.
Quickly select an item from the menu by typing its name while the menu is open.
This also works with the dash.

Preview language-specific forms by enabling “Localized Forms” from the menu.
Pick the desired script and language from the bottom of the features menu.
For this to work, a `locl` feature with valid language-specific rules must be present in “File” → “Font Info…” → “Features”.

In Edit View, Glyphs previews substitution, kerning, and cursive attachment positioning features.
Other positioning features may be handled differently in third-party applications and are not previewed in Edit View.

Test these features directly in software by exporting the fonts.
When testing in Adobe applications, export the fonts to the Adobe Fonts folder.
For details, see Previewing in Adobe Applications.
Note that in InDesign, the OpenType features may be interpreted differently by different composers.

#### Previewing Interpolated Instances

Click the Preview button (an eye) in the bottom-left of the window to preview font instances.
The window content will be split with Edit View above and Preview Area below.
Drag the separator to adjust the size of the Preview Area.

Alternatively, open a separate window which can also be placed on a second display via “Window” → “Preview Panel”.
The Preview Panel displays the Edit View glyphs of the current font file.
When no Edit View tab is currently active, the Preview Panel stays blank.
Click an Edit View tab, and the Preview Panel will immediately update to show the respective glyphs.

Select the instance to be previewed from the pop-up menu in the bottom-left of the preview.
“Show All Instances” displays the current glyph across all instances of the font.
Toggle the display of individual instances in “Show All Instances” by clicking the eye / icon next to an instance name.
Select the dash (-) for the preview to mirror the master used in Edit View.

Except for the “Show All Instances” option, the Preview Area and Preview Panel render the complete text of the current Edit View tab on a single line.
The current glyph is centered by default.
Drag the text horizontally in the Preview Area to reposition it.
Double-click a previewed glyph to edit it.
The rendering respects some custom parameters, as well as intermediate and alternate layers.
Control-click or right-click the Preview Area and choose “Always Center Active Glyph” to keep the active glyph centered.
If deactivated, Glyphs will try to fill the Preview Area as best as possible, keeping the text flush left or flush right.

Switch between black-on-white and white-on-black with the Invert  button next to the instances pop-up menu.
With the Flip / button, flip the Preview upside-down.
Flipping text can be helpful when testing the spacing of a font.
Test the legibility of the font by blurring the font sample in the Preview with the slider next to the Flip button.

#### Previewing on macOS

Applications on the Mac cache font files.
Caching fonts is an optimization that makes sense for most Mac users, since those fonts are typically installed just once and accessed many times by many applications.
However, when creating fonts with Glyphs, the fonts that have already been cached prevent their subsequent exported versions from showing up in apps.
There are multiple approaches to bypass font caching.

Firstly, quit and relaunch the app in which the fonts are previewed.
For example, when testing a font in Pages, save the document and quit Pages.
Export the new version of the font and relaunch Pages.

If this approach does not work, check “Test Install” in the OTF export dialog.
This option writes the font data directly to the system memory without creating a new font file.
Quitting and relaunching may still be required for the new font version to show up.

If the new font versions still do not show up, restart the Mac.
In case that does not fix the issue either, uninstall the affected fonts from the system by deleting them in Font Book.
Then, quit all applications and launch the Terminal application.
Enter the following lines and press the Return key after each line.
If prompted for the user password, note that entering the password does not display the typical ••• bullet points.
Press Return to confirm the password.

```shell
sudo atsutil databases -remove
atsutil server -shutdown
atsutil server -ping
```

After running the three lines above, restart the Mac for the changes to take effect.

If the problem persists, reboot the Mac in safe mode by pressing Cmd-S at startup until the Apple logo appears.
Following that, recreate the caches by holding down Shift while the computer completes the restart and keep holding it while logging in.

#### Previewing in Adobe Applications

For a complete font preview, including positioning features and menu order, open the export dialog (“File” → “Export”, Cmd-E) and choose the OTF export.

Set the path in “Export Destination” to `/Library/Application Support/Adobe/Fonts`.
For this, first, click the folder path to open the folder browser.
Then, press Cmd-Shift-G and enter the path of the Adobe Fonts folder exactly as above.

If the error message “The folder can’t be found.” appears, remove the `/Fonts` at the end of the text field and press “Go” again.
Now create the folder by clicking “New Folder” or by pressing Cmd-Shift-N.
Enter “Fonts” and confirm with “Create”.

Click “Go” and then click “Open” to choose the Adobe Fonts folder and export the fonts by clicking “Next…”

The font becomes immediately available in all Adobe applications.
Glyphs will overwrite any previously saved instance of the font in this folder.
The font will not be available outside Adobe apps, but this is a convenient way to circumvent any font cache problems in macOS.

Adobe apps may need to be closed and relaunched the first time the Adobe Fonts folder is used.
After that, the Adobe font menus will update immediately every time the font is exported.

#### Previewing in Web Browsers

In the export dialog (“File” → “Export”, Cmd-E), check the “.woff2” option to export to WOFF2 font files.
A “.woff” option for older browsers is also available.

These webfont files can be loaded into an HTML webpage and previewed in a web browser.
Reload the webpage to see the new versions of the exported fonts.
The font cache of many browsers can be bypassed by holding down the Shift key while reloading.

A simple HTML file might look like this:

```html
<!DOCTYPE html>
<html lang="en">
  <meta charset="utf-8">
  <title>Webfont Preview</title>
  <meta name="viewport" content="width=device-width">
  <style>
    @font-face {
      font-family: 'Some Font Name';
      src: url(some-font-name.woff2) format('woff2');
    }
    html {
      font-family: 'Some Font Name';
    }
  </style>
  This is the test text for the webfont preview.
</html>
```