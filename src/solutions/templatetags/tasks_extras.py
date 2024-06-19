from django import template
import os

register = template.Library()

def uploadsleft(value, arg):
	left = value - arg.count()
	if left < 0:
		return 0
	return left

register.filter('uploadsleft', uploadsleft)

# This is a modified version of Django's built-in dictsort filter
def basenamedictsort(value, arg):
	parts = arg.split('.')
	def nested_basename(value):
		for part in parts:
			try:
				value = value[part]
			except (AttributeError, IndexError, KeyError, TypeError, ValueError):
				value = getattr(value, part)
		return os.path.basename(value)
	return sorted(value, key=nested_basename)

register.filter('basenamedictsort', basenamedictsort)
