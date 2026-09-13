### Addons

Glyphs can be extended with plug-ins, scripts, and modules from the Plugin Manager.
The “Addons” settings control how these extensions work and which extensions are available.

#### Python version

Python is a programming language popular among type designers and font engineers.
The Python language is under active development, and new versions with new features are released regularly.
Some plug-ins or scripts may require a specific Python version.

Most Glyphs plug-ins and scripts require Python.
Select the version of Python that Glyphs should use for plug-ins and scripts from the “Python version” field.
Note that Glyphs requires Python version 3 or later.

If no Python version is selected or the currently selected version does not work with the installed scripts and plug-ins, go to the menu bar and choose “Window” → “Plugin Manager” → “Modules” and install “Python”.
Switch back to the settings window and choose the Python version labeled “(Glyphs)”.

Relaunch Glyphs for the Python version change to take effect.

#### Console Output

“Use system console for script output” directs the log output of plug-ins and scripts to the system console instead of the Macro Panel console (“Window” → “Macro Panel”, Cmd-Opt-M).
Select this option for debugging a plug-in or script when the Macro Panel is inaccessible.

#### Alternate Plugin Repositories

A plug-in repository defines a set of plug-ins, scripts, and modules that can be installed from the Plugin Manager.
In Glyphs, there is a main plug-in repository that is accessible to all Glyphs users.
It provides some of the most popular Glyphs plug-ins, scripts, and modules.

Glyphs supports alternate plug-in repository URLs with HTTP Basic authentication over HTTPS, which requires a username and password to access the repository.

Local repositories are supported by adding the full file path instead of a URL to the text field.

Define alternate plug-in repositories in addition to the main repository by adding URLs pointing to plug-in repositories in the “Alternate Plugin Repos” text field, one URL per line.
Alternate plug-in repositories are helpful to distribute preview versions of extensions or for private scripts and plug-ins shared within a company.

For the file structure, reference the main plug-in repository.
A repository definition file must follow this structure:

```plist
{
  packages = {
    plugins = (
      {
        titles = {
          en = "Some Plugin";
        };
        url = "https://github.com/example/plugin";
        path = "Some Plugin.glyphsPlugin";
        descriptions = {
          en = "A description of the plugin.";
        };
        screenshot = "https://example.org/image.png";
      },
      ...
    );
    scripts = ( ... );
    modules = ( ... );
  };
}
```

See the main plug-in repository for all available fields.
Only the lists currently in use must be specified.
For example, when only distributing scripts, the `plugins`, and `modules` values may be left off.

The `titles` and `descriptions` fields can offer multiple languages.
See the package index website for a list of language codes.
Glyphs requests the `screenshot` URL with an `Accept-Language` HTTP header, allowing the server to respond with a localized screenshot.