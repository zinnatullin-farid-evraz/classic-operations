import threading
from types import TracebackType
from typing import Callable, List, Optional, Type, Iterable

from .local_dict import ScopedProperty


Callback = Callable[[], None]


class Operation:
    _calls_count: int

    def __init__(
        self,
        on_start: List[Callback] = None,
        on_complete: List[Callback] = None,
        on_cancel: List[Callback] = None,
        on_finish: List[Callback] = None,
    ):
        self._on_start = on_start or []
        self._on_complete = on_complete or []
        self._on_cancel = on_cancel or []
        self._on_finish = on_finish or []

        self._calls_count = 0

    def __enter__(self) -> 'Operation':
        if self._calls_count == 0:
            self._start()

        self._calls_count += 1
        return self

    def __exit__(
        self, exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:

        self._calls_count -= 1

        if self._calls_count == 0:
            if exc_type is None:
                self._complete()
            else:
                self._cancel()

        return False

    @property
    def in_process(self):
        return self._calls_count > 0

    def before_complete(self, callback: Callback):
        assert self.in_process
        self._on_complete.insert(0, callback)

    def after_complete(self, callback: Callback):
        assert self.in_process
        self._on_complete.append(callback)

    def on_cancel(self, callback: Callback):
        assert self.in_process
        self._on_cancel.append(callback)

    def on_finish(self, callback: Callback):
        assert self.in_process
        self._on_finish.append(callback)

    @staticmethod
    def _handle_all(callbacks: Iterable[Callback]):
        errors = []
        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise RuntimeError(errors)

    @staticmethod
    def _handle_for_first_error(callbacks: Iterable[Callback]):
        for callback in callbacks:
            callback()

    def _start(self):
        try:
            self._handle_for_first_error(self._on_start)
        except Exception:
            self._cancel()
            self._finish()
            raise

    def _complete(self):
        try:
            self._handle_for_first_error(self._on_complete)
        except Exception:
            self._cancel()
            raise
        finally:
            self._finish()

    def _cancel(self):
        self._handle_all(self._on_cancel)

    def _finish(self):
        self._handle_all(self._on_finish)


class NewOperation:
    on_start: List[Callback] = None,
    on_complete: List[Callback] = None,
    on_cancel: List[Callback] = None,
    on_finish: List[Callback] = None,

    def __init__(
        self,
        on_start: List[Callback] = None,
        on_complete: List[Callback] = None,
        on_cancel: List[Callback] = None,
        on_finish: List[Callback] = None,
    ):
        self._on_start = on_start or []
        self._on_complete = on_complete or []
        self._on_cancel = on_cancel or []
        self._on_finish = on_finish or []

    def __call__(self):
        return Operation(
            on_start=self._on_start.copy(),
            on_complete=self._on_complete.copy(),
            on_cancel=self._on_cancel.copy(),
            on_finish=self._on_finish.copy(),
        )


class NewScopedOperation(NewOperation):

    def __init__(self, *args):
        super().__init__(*args)
        self._storage = threading.local()

    def __call__(self):
        try:
            operation = self._storage.operation
        except AttributeError:
            operation = super().__call__()
            self._storage.operation = operation
        else:
            if not operation.in_process:
                operation = super().__call__()
                self._storage.operation = operation

        return operation


class NewFastScopedOperation(NewOperation):
    _current = ScopedProperty()

    def __call__(self):
        try:
            operation = self._current
        except KeyError:
            operation = super().__call__()
            self._current = operation
        else:
            if not operation.in_process:
                operation = super().__call__()
                self._current = operation

        return operation
