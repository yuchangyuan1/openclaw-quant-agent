from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def call_with_retry(
    func: Callable[[], T],
    *,
    attempts: int = 2,
    retriable_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> tuple[T, int]:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func(), attempt
        except retriable_exceptions as exc:
            last_error = exc
            if attempt == attempts:
                raise
    assert last_error is not None
    raise last_error
