# youseedee: interface to the UCD"

This module allows you to query the Unicode Character Database. The main
function to be imported is `ucd_data`:

    >>> ucd_data(0x078A)
    {'Age': '3.0',
     'Block': 'Thaana',
     'Canonical_Combining_Class': '0',
     'East_Asian_Width': 'N',
     'General_Category': 'Lo',
     'Line_Break': 'AL',
     'Name': 'THAANA LETTER FAAFU',
     'Script': 'Thaana'}

On first run, it will download the database files for you from
unicode.org. These are stored in your operating system's user cache directory (determined by [`platformdirs`](https://pypi.org/project/platformdirs/)) in a folder called `youseedee`.
These are also updated if new data is available from unicode.org

You may also use it as a command line utility:

    $ python3 -m youseedee 0x078A
    {'Age': '3.0',
     'Block': 'Thaana',
     'Canonical_Combining_Class': '0',
     'East_Asian_Width': 'N',
     'General_Category': 'Lo',
     'Line_Break': 'AL',
     'Name': 'THAANA LETTER FAAFU',
     'Script': 'Thaana'}

    $ python3 -m youseedee Ǩ
    {'Age': '1.1',
     'Block': 'Latin Extended-B',
     'Canonical_Combining_Class': '0',
     'Case_Folding_Mapping': '01E9',
     'Case_Folding_Status': 'C',
     'East_Asian_Width': 'N',
     'General_Category': 'Lu',
     'Line_Break': 'AL',
     'Name': 'LATIN CAPITAL LETTER K WITH CARON',
     'Script': 'Latin'}
