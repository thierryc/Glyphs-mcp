#### Roughen

“Filter” → “Roughen” segments an outline into straight line segments and randomly moves all resulting nodes within a given limit.
Control the size of the line segments with the “Segment Length” field.
The “Horizontal” and “Vertical” values control the maximum offset for each node.
The custom parameter rule is as follows:

```filter
Roughenizer; `Length`; `Horizontal`; `Vertical`
```

For example, the following rule would match the “Roughen” dialog window shown above:

```filter
Roughenizer; 15; 15; 10
```