"""Shared result and error types for Python CLI and parsing utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum, auto
from functools import wraps
from typing import (
    ClassVar,
    Generic,
    NoReturn,
    ParamSpec,
    TypeAlias,
    TypeVar,
    cast,
)


class CliError(Enum):
    """Enumerate failure modes encountered during CLI argument parsing."""

    UNKNOWN_ARGUMENT = auto()
    MISSING_REQUIRED_ARGUMENT = auto()
    INVALID_CHOICE = auto()
    INVALID_ARGUMENT_TYPE = auto()
    MISSING_ARGUMENT_VALUE = auto()


E = TypeVar("E", bound=Enum)
F = TypeVar("F", bound=Enum)
T = TypeVar("T")
R = TypeVar("R")
U = TypeVar("U")
P = ParamSpec("P")


@dataclass(frozen=True)
class Diagnostic:
    """Stores the error location and context for diagnostic reporting."""

    filename: str
    line_num: int
    line_text: str
    col_start: int
    col_end: int
    help_msg: str | None = None


class BubbleUpError(Exception):
    """Internal exception to bubble Err results up to a catch_bubble
    decorator."""

    def __init__(self, err_payload: Err[E]):
        """Store the error being propagated."""
        super().__init__(f"BubbleUpError: {err_payload.error}")
        self.err_payload = err_payload


def catch_bubble(func: Callable[P, R]) -> Callable[P, R]:
    """Decorate a function to convert bubbled errors into return values.

    Returns:
        A wrapper that catches and returns bubbled error payloads.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except BubbleUpError as error:
            return cast(R, error.err_payload)

    return wrapper


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Wrap a successful result value of type T."""

    value: T

    def is_ok(self) -> bool:
        """Return whether this result is successful.

        Returns:
            True because this instance represents an Ok value.
        """
        return True

    def is_err(self) -> bool:
        """Return whether this result is an error.

        Returns:
            False because this instance represents an Ok value.
        """
        return False

    def is_ok_and(self, predicate: Callable[[T], bool]) -> bool:
        """Return whether the value satisfies a predicate.

        Args:
            predicate: Function used to test the contained value.

        Returns:
            The boolean result returned by ``predicate``.
        """
        return predicate(self.value)

    def is_err_and(self, _predicate: Callable[[object], bool]) -> bool:
        """Return whether an error satisfies a predicate.

        Args:
            _predicate: Error predicate that is not evaluated for Ok.

        Returns:
            False because this result contains no error.
        """
        return False

    def unwrap(self) -> T:
        """Return the contained successful value.

        Returns:
            The value stored by this Ok instance.
        """
        return self.value

    def expect(self, _message: str) -> T:
        """Return the contained successful value.

        Args:
            _message: Error message that would be used for an Err value.

        Returns:
            The value stored by this Ok instance.
        """
        return self.value

    def unwrap_err(self) -> NoReturn:
        """Reject unwrapping an error from an Ok result.

        Raises:
            ValueError: Always, because this result contains no error.
        """
        raise ValueError("Called `Result::unwrap_err()` on an `Ok` value")

    def expect_err(self, message: str) -> NoReturn:
        """Reject an Ok result using a caller-provided message.

        Args:
            message: Error message used for the raised exception.

        Raises:
            ValueError: Always, because this result contains no error.
        """
        raise ValueError(message)

    def unwrap_or(self, _default: U) -> T:
        """Return the successful value instead of a fallback.

        Args:
            _default: Fallback value that is ignored for Ok.

        Returns:
            The value stored by this Ok instance.
        """
        return self.value

    def unwrap_or_else(self, _func: Callable[[object], U]) -> T:
        """Return the successful value without computing a fallback.

        Args:
            _func: Fallback function that is not called for Ok.

        Returns:
            The value stored by this Ok instance.
        """
        return self.value

    def map(self, func: Callable[[T], U]) -> Ok[U]:
        """Transform the contained successful value.

        Args:
            func: Function applied to the contained value.

        Returns:
            A new Ok containing the transformed value.
        """
        return Ok(func(self.value))

    def map_err(self, _func: Callable[[object], F]) -> Ok[T]:
        """Leave an Ok unchanged when mapping errors.

        Args:
            _func: Error transformation function that is not called.

        Returns:
            This Ok instance unchanged.
        """
        return self

    def inspect(self, func: Callable[[T], object]) -> Ok[T]:
        """Call a function with the successful value without changing it.

        Args:
            func: Function called with the contained value.

        Returns:
            This Ok instance unchanged.
        """
        func(self.value)
        return self

    def inspect_err(self, _func: Callable[[object], object]) -> Ok[T]:
        """Leave an Ok unchanged when inspecting errors.

        Args:
            _func: Error inspection function that is not called.

        Returns:
            This Ok instance unchanged.
        """
        return self

    def and_(self, other: Result[U, E]) -> Result[U, E]:
        """Return another result when this result is Ok.

        Args:
            other: Result returned in place of this successful result.

        Returns:
            ``other`` unchanged.
        """
        return other

    def and_then(
        self,
        func: Callable[[T], Result[U, E]],
    ) -> Result[U, E]:
        """Apply a fallible transformation to the successful value.

        Args:
            func: Function receiving the contained value and returning a
                new Result.

        Returns:
            The Result returned by ``func``.
        """
        return func(self.value)

    def or_(self, _other: Result[U, F]) -> Result[T, F]:
        """Keep this successful result instead of an alternative result.

        Args:
            _other: Alternative result that is ignored because this
                result is Ok.

        Returns:
            This Ok value, typed with the alternative error type.
        """
        return self

    def or_else(
        self,
        _func: Callable[[object], Result[U, F]],
    ) -> Result[T, F]:
        """Keep this successful result without computing an alternative.

        Args:
            _func: Function that would produce an alternative Result for
                an Err value. It is not called for Ok.

        Returns:
            This Ok value, typed with the alternative error type.
        """
        return self

    def ok(self) -> Some[T]:
        """Convert this successful result into Some.

        Returns:
            A Some containing the successful value.
        """
        return Some(self.value)

    def err(self) -> Nothing:
        """Convert the absent error into Nothing.

        Returns:
            A Nothing value because this result contains no error.
        """
        return Nothing()

    def iter(self) -> Iterator[T]:
        """Iterate over the successful value.

        Yields:
            The contained value exactly once.
        """
        yield self.value

    @property
    def q(self) -> T:
        """The successful value used for Rust-like propagation.

        Returns:
            The contained successful value.
        """
        return self.value


@dataclass(frozen=True)
class Err(Generic[E]):
    """Wrap failure results with error variants and optional diagnostics."""

    error: E
    diagnostic: Diagnostic | None = None
    context_msg: str | None = None
    PROJECT_NAME: ClassVar[str] = "pacman"
    namespace: str | None = None

    def unwrap(self) -> NoReturn:
        """Print diagnostic context and reject unwrapping an error.

        Raises:
            ValueError: Always, because an error has no success value.
        """
        self.print_diagnostic()
        raise ValueError(f"Called `Result::unwrap()` on an `Err` value: {self.error.name}")

    def print_diagnostic(self) -> None:
        """Prints a diagnostic message with dynamic caret alignment."""
        RED = "\033[1;31m"
        PINK = "\033[1;35m"
        BLUE = "\033[1;34m"
        CYAN = "\033[1;36m"
        RESET = "\033[0m"
        BOLD = "\033[1m"

        if self.namespace:
            sub_ns = self.namespace.lower().strip(":")
        else:
            raw_classname = self.error.__class__.__name__
            sub_ns = raw_classname.removesuffix("Error").lower()

        err_name_str = str(self.error.name).lower().replace("_", "::")
        full_namespace = f"{self.PROJECT_NAME}::{sub_ns}::{err_name_str}"

        print(f"{BOLD}Error:{RESET} {PINK}{full_namespace}{RESET}\n")

        if not self.diagnostic:
            print(f" {RED}×{RESET} {BOLD}Operation failed{RESET}")
            print(f"   {RED}╰─▶{RESET} {err_name_str.replace('_', ' ').title()}")
            return

        d = self.diagnostic
        summary = self.context_msg or "Validation failed"
        print(f" {RED}×{RESET} {BOLD}{summary}{RESET}")
        print(
            f"   {BLUE}╭─[{RESET}{BOLD}{d.filename}:"
            f"{d.line_num}:{d.col_start + 1}{RESET}{BLUE}]{RESET}"
        )
        print(f"{d.line_num:2} {BLUE}│{RESET} {d.line_text}")

        hook_text = "╰─── "
        prefix = f"{RED}{hook_text}{BOLD}"
        carets = "^" * max(1, (d.col_end - d.col_start))
        hook_width = len(hook_text)

        if d.col_start >= hook_width:
            padding = " " * (d.col_start - hook_width)
            print(f"   {BLUE}·{RESET} {padding}{prefix}{carets}{RESET}")
        else:
            padding = " " * d.col_start
            print(f"   {BLUE}·{RESET} {padding}{RED}{carets}{RESET}")

        if d.help_msg:
            print(f"\n   {CYAN}help:{RESET} {d.help_msg}")

    @property
    def q(self) -> NoReturn:
        """Propagate this error to a ``catch_bubble`` wrapper.

        Raises:
            BubbleUpError: Always, carrying this error result.
        """
        raise BubbleUpError(self)


Result: TypeAlias = Ok[T] | Err[E]


class BubbleUpNothing(Exception):
    """Internal exception used to bubble Nothing through a decorator."""

    nothing: Nothing

    def __init__(self, nothing: Nothing) -> None:
        """Store the absent option being propagated."""
        super().__init__("Attempted to bubble up Nothing")
        self.nothing = nothing


@dataclass(frozen=True)
class Some(Generic[T]):
    """Wrap a present optional value."""

    value: T

    def is_some(self) -> bool:
        return True

    def is_none(self) -> bool:
        return False

    def is_some_and(self, predicate: Callable[[T], bool]) -> bool:
        return predicate(self.value)

    def unwrap(self) -> T:
        return self.value

    def expect(self, _message: str) -> T:
        return self.value

    def unwrap_or(self, _default: T) -> T:
        return self.value

    def unwrap_or_else(self, _func: Callable[[], T]) -> T:
        return self.value

    def map(self, func: Callable[[T], R]) -> Some[R]:
        return Some(func(self.value))

    def inspect(self, func: Callable[[T], object]) -> Some[T]:
        func(self.value)
        return self

    def filter(self, predicate: Callable[[T], bool]) -> Option[T]:
        return self if predicate(self.value) else Nothing()

    def and_(self, other: Option[R]) -> Option[R]:
        return other

    def and_then(self, func: Callable[[T], Option[R]]) -> Option[R]:
        return func(self.value)

    def or_(self, _other: Option[T]) -> Option[T]:
        return self

    def or_else(self, _func: Callable[[], Option[T]]) -> Option[T]:
        return self

    def xor(self, other: Option[T]) -> Option[T]:
        return Nothing() if isinstance(other, Some) else self

    def ok_or(self, _error: E) -> Result[T, E]:
        return Ok(self.value)

    def ok_or_else(self, _func: Callable[[], E]) -> Result[T, E]:
        return Ok(self.value)

    def iter(self) -> Iterator[T]:
        yield self.value

    @property
    def q(self) -> T:
        """The contained value used for propagation."""
        return self.value


@dataclass(frozen=True)
class Nothing:
    """Represent the absence of a value."""

    def is_some(self) -> bool:
        return False

    def is_none(self) -> bool:
        return True

    def is_some_and(self, _predicate: Callable[[object], bool]) -> bool:
        return False

    def unwrap(self) -> NoReturn:
        raise ValueError("Called `Option::unwrap()` on a `Nothing` value")

    def expect(self, message: str) -> NoReturn:
        raise ValueError(message)

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_or_else(self, func: Callable[[], T]) -> T:
        return func()

    def map(self, _func: Callable[[object], R]) -> Nothing:
        return self

    def inspect(self, _func: Callable[[object], object]) -> Nothing:
        return self

    def filter(self, _predicate: Callable[[object], bool]) -> Nothing:
        return self

    def and_(self, _other: Option[R]) -> Nothing:
        return self

    def and_then(self, _func: Callable[[object], Option[R]]) -> Nothing:
        return self

    def or_(self, other: Option[T]) -> Option[T]:
        return other

    def or_else(self, func: Callable[[], Option[T]]) -> Option[T]:
        return func()

    def xor(self, other: Option[T]) -> Option[T]:
        return other

    def ok_or(self, error: E) -> Result[object, E]:
        return Err(error)

    def ok_or_else(self, func: Callable[[], E]) -> Result[object, E]:
        return Err(func())

    def iter(self) -> Iterator[object]:
        return iter(())

    @property
    def q(self) -> NoReturn:
        raise BubbleUpNothing(self)


Option: TypeAlias = Some[T] | Nothing


def catch_nothing(
    func: Callable[P, Option[T]],
) -> Callable[P, Option[T]]:
    """Convert bubbled Nothing values into returned Nothing values.

    Returns:
        A wrapper that catches propagated absence.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Option[T]:
        try:
            return func(*args, **kwargs)
        except BubbleUpNothing as bubbled:
            return bubbled.nothing

    return wrapper
