:mod:`GSCustomParameter`
===============================================================================

Implementation of the Custom Parameter object. It stores a name/value pair.

You can append GSCustomParameter objects for example to GSFont.customParameters, but this way you may end up with duplicates.
It is best to access the custom parameters through its dictionary interface like this:

.. code-block:: python
	# access all parameters
	for parameter in font.customParameters:
	    print(parameter)

	# set a parameter
	font.customParameters['trademark'] = 'ThisFont is a trademark by MyFoundry.com'

	# add multiple parameters:
	parameter = GSCustomParameter("Name Table Entry", "1 1;"font name")
	font.customParameters.append(parameter)
	parameter = GSCustomParameter("Name Table Entry", "2 1;"style name")
	font.customParameters.append(parameter)

	# delete a parameter
	del font.customParameters['trademark']

.. class:: GSCustomParameter([name, value])

	:param name: The name
	:param value: The value
