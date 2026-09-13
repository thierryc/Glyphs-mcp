### Scripts

Scripts are written in the Python programming language and can automate every part of Glyphs.
Some scripts require specific modules to be installed; install these from the “Modules” tab in the Plugin Manager.

#### Run Scripts

Access all installed scripts from the “Script” menu.
Many scripts show a short description when the mouse pointer rests on its menu item for a few seconds.
Click a menu item to run the script.

Assign a keyboard shortcut to a script to run it with a key press.
See Shortcuts for details.
Re-run the last script with Cmd-Opt-R or from the bottom of the “Script” menu.

#### The Scripts Folder

The “Script” menu reflects the files of the Scripts folder.
Open the Scripts folder with “Script” → “Open Scripts Folder” (Cmd-Shift-Y).
Reload the “Script” menu by holding down the Option key and choosing “Script” → “Reload Scripts” (Cmd-Opt-Shift-Y).

#### Creating Scripts

Add scripts by creating a file ending in “.py” in the Scripts folder.
The part of the filename before the “.py” is arbitrary, but for clarity, it is recommended to name the file as it should appear in the “Script” menu, for example, “Some Script.py”.
Create subfolders to group scripts.
Inside the Python file, add a comment at the top with the following format:

```python
# MenuTitle: `Script Name`
```

Replace `Script Name` with the name that should be displayed in the “Script” menu.
Add a description that is shown when the mouse pointer rests on the menu item by writing the following code below the `# MenuTitle` line:

```python
__doc__="`Description`"
```

Replace `Description` with a short description of the script.
The description can span multiple lines:

```python
__doc__="""
This description spans multiple lines.
Here is the second line.
"""
```

For writing the actual script, consult the Glyphs Python API documentation.
On the Glyphs website, there is a tutorial series from the first steps of programming in Python up to writing advanced scripts.
Viewing the code of existing scripts is also a great way to learn.
If any questions arise, feel free to ask on the Glyphs forum or contact the Glyphs team directly.