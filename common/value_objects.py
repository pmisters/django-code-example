import abc
import dataclasses
import datetime
from decimal import Decimal
from enum import Enum
from traceback import TracebackException
from typing import Any, Dict, List, TypeVar

from returns.result import Failure, Result


@dataclasses.dataclass
class CaseError:
    container: Any = None
    ctx: Any = None
    error: str = ''
    exc: Exception = None
    failure: Enum = None

    def __str__(self) -> str:
        result = []
        if self.error:
            result.append(f"{self.error}")
        if self.container is not None:
            result.append(f"in {self.container.__class__.__module__}.{self.container.__class__.__name__}")
        if self.ctx is not None:
            result.append(f"\nCONTEXT: {self.ctx!r}")
        if self.exc is not None and isinstance(self.exc, Exception):
            _exc = ''.join(TracebackException.from_exception(self.exc).format())
            result.append(f"\nTRACE: {_exc}")
        return ' '.join(result)

    def short_info(self) -> str:
        result = []
        if self.error:
            result.append(f"{self.error}")
        if self.container is not None:
            result.append(f"in {self.container.__class__.__module__}.{self.container.__class__.__name__}")
        if self.exc is not None and isinstance(self.exc, Exception):
            result.append(f"\nEXCEPTION: {self.exc.__class__.__name__}({self.exc})")
        return ' '.join(result)


class ServiceBase(abc.ABC):
    @abc.abstractmethod
    def execute(self, *args, **kwargs):
        pass

    def _error(self, error: str, ctx: Any = None, failure: Enum = None, exc: Exception = None) -> Failure:
        return Failure(CaseError(container=self, ctx=ctx, error=error, failure=failure, exc=exc))


# Types

_ValueType = TypeVar('_ValueType', covariant=True)
ResultE = Result[_ValueType, CaseError]
TCalendarDates = Dict[int, List[datetime.date]]
TPrices = Dict[datetime.date, Decimal]
TRecord = Dict[str, Any]
