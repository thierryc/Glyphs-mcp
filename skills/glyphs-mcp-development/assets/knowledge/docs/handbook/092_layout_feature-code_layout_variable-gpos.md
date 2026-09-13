### Variable GPOS

Position (`pos`) rules can be contextualized to specific regions of the designspace.
Write axis tags and their internal coordinates in parentheses, followed by the value to be used at that location of the designspace.
For example, in the `cpsp` feature:

```fea
pos @Uppercase 10;              # static
pos @Uppercase 10 (wdth:80) 20; # variable
```

There can be multiple alternative values and axes:

```fea
pos @Uppercase 10 (wdth:80) 20 (wdth:40 opsz:28) 30;
```

The same works for the four-value syntax:

```fea
pos @Digit colon' <10 50 20 0
	(wdth:80) 30 40 60 0
	(wdth:40 opsz:28) 5 10 10 0> @Digit;
```

In a variable font, the position value interpolates smoothly along the specified axes.