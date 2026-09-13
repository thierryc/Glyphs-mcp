### Multiple Languages Syntax

In Glyphs, the `language` keyword may be followed by more than one language tag:

```fea
language ENG DEU FRA;
```

Without this syntax extension, rules that do not apply to the default language need to be repeated for every language for which they apply.
For example:

```fea
script latn;
language AZE;
	sub i by idotaccent;
language CRT;
	sub i by idotaccent;
language KAZ;
	sub i by idotaccent;
language TAT;
	sub i by idotaccent;
language TRK;
	sub i by idotaccent;
```

The above code can be shortened to the following:

```fea
script latn;
language AZE CRT KAZ TAT TRK;
	sub i by idotaccent;
```