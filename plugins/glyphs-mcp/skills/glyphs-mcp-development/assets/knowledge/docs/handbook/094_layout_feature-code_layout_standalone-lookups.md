### Standalone Lookups

Lookups written inside a `feature` block are applied when the feature is enabled by the typesetting system.
Commonly, this is the intended behavior.

Some lookups, however, should not be applied directly by the feature.
Instead, they are used as part of a different lookup, for example via a chaining substitution.
In such cases, the definition lookup needs to be moved outside of the `feature` block.
In Glyphs, this is done by writing the lookup definition in a “Prefix” section.
However, since the “Prefix” code is placed before the “Features” code, and lookups are applied in the order in which they are written, such prefix lookups might get applied too early.

Resolve this issue by writing the `standalone` keyword before the `lookup` keyword when defining a lookup inside a feature.
This will apply the lookup only when used from other lookups, while keeping the order of the lookup unchanged.

For example, the following is a stand-alone lookup being used as part of a chaining substitution inside the `ccmp` feature:

```fea
standalone lookup demo {
	sub gravecomb by gravecomb.case;
	sub acutecomb by acutecomb.case;
} demo;

sub @Uppercase @CombiningTopAccents' lookup demo;
```

For lookups defined outside of a feature, the `standalone` keyword is redundant and will be ignored.