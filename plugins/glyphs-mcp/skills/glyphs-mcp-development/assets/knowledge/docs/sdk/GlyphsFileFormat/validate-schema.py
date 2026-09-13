import sys
import json
import jsonschema
import openstep_plist


def main():
	if len(sys.argv) != 3:
		print('Usage: python validate-schema.py SCHEMA PLIST')
		sys.exit(1)

	schema_file_path = sys.argv[1]
	plist_file_path = sys.argv[2]

	with open(schema_file_path, 'r') as f:
		schema = json.load(f)

	with open(plist_file_path, 'r') as f:
		plist = openstep_plist.load(f, use_numbers=True)

	jsonschema.validate(plist, schema)


if __name__ == '__main__':
	main()
