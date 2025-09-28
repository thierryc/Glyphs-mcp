### Custom Feature Code Snippets

When editing OpenType layout feature code, click the snippets  button located in the bottom-right of the window.
Choose “Show Snippet Folder” to reveal the folder in which additional snippets can be placed.
Snippets are defined in property list files (.plist) named “FeatureSnippetsNAME.plist” where “NAME” is the name of the snippets group.
For example, create a file named “FeatureSnippetsDecomposition.plist”:

```plist
(
  {
    title = "Soft Dotted";
    code = "lookupflag UseMarkFilteringSet @TopMark;
sub @SoftDotted' @TopMark by @Dotless;";
  },
  {
    title = "Decompose Precomposed";
    code = "sub @Precomp' lookup decomp @Mark;";
  }
)
```