### Regular Expressions

Regular expressions (often abbreviated as _regex_) can be used in some search fields to search for text patterns.
For example, `[LlDd]caron` matches any of the following: “Lcaron”, “lcaron”, “Dcaron”, and “dcaron”.
Characters that have a special meaning in patterns (such as `.` or `?`) can be found by prefixing them with a backslash `\`, for example, `\.` or `\?`.

`.`

Matches any character (`a`, `.`, `-`, a space, …).

`[abc]`

Matches any character within the square brackets.
For example, `[ae]acute` matches both “aacute” and “eacute”.

`[^abc]`

Matches any character that is not within the square brackets.
For example, `[^au]-cy` matches “e-cy” and “o-cy” but not “a-cy” or “u-cy”.

`\d`

Matches any digit: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9.
`\D` matches any character except for digits.
For example, `A\.00\d` matches “A.000” and “A.003” but not “A.00F” or “A.123”.

`\w`

Matches _word_ characters: letters, digits, and the underscore (`_`).
This is the same as writing `[a-zA-Z0-9_]`.
For example, `\w+` finds “a” and “alpha”, but not “a-cy”.
`\W` matches any character except for word characters.

`?`

Matches the preceding pattern zero or one time.
For example, `oe?` finds both “o” and “oe”; `[ae]?breve` finds “abreve”, “ebreve”, and “breve”; and `grave(comb)?` finds both “grave” and “gravecomb”.

`*`

Matches the preceding pattern zero or multiple times.
For example, `A.*` finds “A”, “AE”, “Atilde”, and “Alpha”.

`+`

Matches the preceding pattern one or multiple times.
For example, `A.+` finds “AE”, “Atilde”, and “Alpha”, but not “A”.

`{n}`

Matches the preceding pattern _n_ times.
For example, `a{5}` only finds “aaaaa” and `\d{3}` finds “000” and “123” but not “12” or “1234”.

`{n,m}`

Like `{n}`, but finds the preceding pattern between _n_ and _m_ times.
_n_ may be `0` and _m_ may be left off not to set an upper limit.
`a{0,1}` is the same as `a?`, `a{0,}` is the same as `a*`, and `a{1,}` is the same as `a+`.
For example, `\d{3,5}` finds “123”, “1234”, and “12345”, but not “12” or “123456”.

Useful patterns include:

`a.*`

Matches any glyph that starts with “a”.

`.*a`

Matches any glyph that ends with “a”.

`.*-.*`

Matches any glyph that contains a hyphen.

`.*\..*`

Matches any glyph that contains a dot.

`.*\.\d+`

Matches any glyph that ends in a dot followed by digits.

`\D*\.\d{3}`

Matches any glyph that ends in a dot and three digits and does not contain any digits before that.

When finding and replacing with regular expressions, use `\1`, `\2`, … to insert parts of the found pattern in the replacement.
The parts must be enclosed in round parenthesis in the find pattern.
In the replacement pattern, use a backslash followed by the number referencing the parenthesized part.

For example, search for `(\d)(\d)` and replace it with `\2\1` to swap two digits (“15” becomes “51” or “03” becomes “30”).
See also Search Field.