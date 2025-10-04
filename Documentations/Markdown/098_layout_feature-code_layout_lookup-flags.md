### Lookup Flags

The `lookupflag` keyword resets any previous lookup flags and sets a new set of flags.
For example, to reset the previous flags and ignore marks in the current lookup, the following code line can be placed at the start of a lookup definition:

```fea
lookupflag IgnoreMarks;
```

When writing lookups, it is common to ignore any prior flags without setting new ones.
In the standard feature syntax this is done by using the special flag `0`:

```fea
lookupflag 0;
```

As an alternative, Glyphs allows resetting lookup flags without setting new flags by simply defining an empty `lookupflag` statement:

```fea
lookupflag;
```