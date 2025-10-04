### Optional Closing Lookup Name

The standard feature syntax requires the name of a lookup to be repeated at the end of the lookup definition:

```fea
lookup some_descriptive_lookup_name {
	# lookup code
} some_descriptive_lookup_name;
```

In Glyphs, the lookup name at the end may be omitted:

```fea
lookup some_descriptive_lookup_name {
	# lookup code
};
```