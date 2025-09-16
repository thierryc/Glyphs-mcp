.. attribute:: date

		:type: datetime.datetime

		.. code-block:: python
			print(font.date)
			>> 2015-06-08 09:39:05

			# set date to now
			font.date = datetime.datetime.now()
			# using NSDate
			font.date = NSDate.date()
			# or in seconds since Epoch
			font.date = time.time()
