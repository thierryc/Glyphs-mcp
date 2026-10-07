# Contribute a skill

1. Choose one repeatable Glyphs or font workflow. Explain when it should and
   should not be invoked, required inputs, outputs and any font-edit permissions.
2. Copy `template/example-skill` to `skills/<your-skill-name>` in a fork, or keep
   the skill in your own public GitHub repository. Keep the folder name and
   frontmatter `name` identical. Use lowercase letters, numbers and hyphens.
3. Include `SKILL.md`, a redistribution license and author attribution. Keep
   references within the skill folder and use relative links. Include scripts
   only where they improve the workflow, with documented dependencies.
4. Provide at least two example prompts, expected results, and one prompt that
   should not trigger the skill. State which clients you actually tested and
   the versions of Glyphs MCP, Glyphs and companions that are required.
5. Open a pull request with the skill and examples. For an externally maintained
   skill, add a registry entry with the public repository, directory, full
   immutable commit, and SHA-256 of its GitHub codeload ZIP. No floating branches,
   tags, arbitrary download hosts or Gist imports are accepted in this version.
6. Run the validator and complete the PR checklist. Maintainers inspect all
   instructions/resources and review compatibility and licensing before merge.

**For skills contributed here:** submit the folder and examples first. A
maintainer merges the reviewed content, calculates the commit/archive checksum,
and adds the catalog entry in a second reviewed PR. This avoids an archive
checksum that depends on the very commit containing it.

**For source updates:** submit a fresh pinned commit and checksum with a summary
of changed behavior and new test evidence. Changes do not silently update
installed copies; users choose Update in the app.

The `bundled` entries are references to canonical Glyphs MCP skills. Never copy,
rename, replace or modify them through a community submission. A compatible
optional skill must have a distinct name.

If making a PR is difficult, use the Submit Skill issue form with your GitHub
link. An issue is a review request, not automatic publication. Maintainers may
ask for a repository-based submission when additional files are needed.

Do not include credentials, unsaved user fonts, private reports, executable
install hooks, or claims that installing instructions grants tool permissions.
Record live verification only on disposable fonts and keep saves/exports within
explicit authorization. An instruction-only skill is a good first contribution.

## Registry entry

Use `registry-v1.schema.json`. Required fields include `id`, `name`, description,
author, license, `classification` (`community` for submissions), pinned `source`,
`compatibleClients`, `requirements`, and `bundled: false`. The ID should be
`<author>/<skill-name>` and must remain stable when a revision changes.

For example, compute an external archive checksum without executing its files:

```sh
curl --fail --location https://codeload.github.com/OWNER/REPOSITORY/zip/FULL_COMMIT -o source.zip
shasum -a 256 source.zip
```

Review findings belong in the PR. Passing automated checks does not itself
establish that a skill is suitable or compatible.
