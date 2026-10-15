import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('validate_catalog', Path(__file__).resolve().parents[1]/'scripts/validate_catalog.py')
validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)


class ValidationTests(unittest.TestCase):
    def test_seed_and_template(self):
        self.assertEqual(validator.validate(), 12)

    def test_plain_and_block_metadata(self):
        parsed = validator.metadata(b'---\nname: test-skill\ndescription: >-\n  A focused\n  workflow\n---\n')
        self.assertEqual(parsed['description'], 'A focused workflow')

    def test_duplicate_and_unsafe_metadata(self):
        for source in [b'---\nname: x\nname: y\ndescription: z\n---', b'---\nname: ../x\ndescription: z\n---']:
            with self.assertRaises(ValueError): validator.metadata(source)

    def test_missing_and_escaping_references(self):
        for reference in ['missing.md', '../outside.md']:
            with self.assertRaises(ValueError):
                validator.validate_files({'SKILL.md': ('---\nname: test\ndescription: test\n---\n[ref]('+reference+')').encode()})

    def test_nested_reference_stays_in_package(self):
        validator.validate_files({'SKILL.md': b'---\nname: test\ndescription: test\n---\n[ref](references/detail.md)',
                                  'references/detail.md': b'[ref](../assets/info.txt)', 'assets/info.txt': b'info'})

    def test_unsafe_paths(self):
        for path in ['../x','/x','a//b','a\\b','a/./b']:
            with self.assertRaises(ValueError): validator.relative(path)
