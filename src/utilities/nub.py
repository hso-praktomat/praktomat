from collections.abc import Hashable, Iterable
from typing import TypeVar


T = TypeVar("T", bound=Hashable)


# http://stackoverflow.com/a/480227/946226
def nub(seq: Iterable[T]) -> list[T]:
    seen: set[T] = set()
    seen_add = seen.add
    return [ x for x in seq if x not in seen and not seen_add(x)]
