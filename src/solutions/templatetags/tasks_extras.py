from django import template
from django.db.models import QuerySet
import os
from collections.abc import Iterable
from typing import Any

from solutions.models import Solution

register = template.Library()


def uploadsleft(value: int, arg: QuerySet[Solution, Solution]) -> int:
	left = value - arg.count()
	if left < 0:
		return 0
	return left

register.filter('uploadsleft', uploadsleft)

# This is a modified version of Django's built-in dictsort filter
def basenamedictsort(value: Iterable[object], arg: str) -> list[object]:
	parts = arg.split('.')
	def nested_basename(value: Any) -> str:
		for part in parts:
			try:
				value = value[part]
			except (AttributeError, IndexError, KeyError, TypeError, ValueError):
				value = getattr(value, part)
		return os.path.basename(value)
	return sorted(value, key=nested_basename)

register.filter('basenamedictsort', basenamedictsort)
