"""Made by Codex to demonstrate every Result and Option case.

Use ``Option[T]`` when a value may normally be absent and the caller only
needs to know whether it exists. For example, searching an empty collection
can return ``Nothing`` without anything having gone wrong.

Use ``Result[T, E]`` when an operation can fail and the caller needs to know
why. Its ``Err`` carries an error category and can include a diagnostic with
source location, context, and recovery guidance.
"""

from collections.abc import Callable

from pacman.errors import (
    CliError,
    Diagnostic,
    Err,
    Nothing,
    Ok,
    Option,
    Result,
    Some,
    catch_bubble,
    catch_nothing,
)


def show(label: str, value: object) -> None:
    """Print one example result with a readable label.

    Args:
        label: Name of the operation being demonstrated.
        value: Value returned by the operation.
    """
    print(f"{label:28} -> {value!r}")


def show_raised(label: str, operation: Callable[[], object]) -> None:
    """Run a deliberately failing operation and display its exception.

    Args:
        label: Name of the operation being demonstrated.
        operation: Zero-argument callable expected to raise ``ValueError``.
    """
    try:
        operation()
    except ValueError as error:
        show(label, f"ValueError: {error}")


@catch_bubble
def divide_then_double(dividend: int, divisor: int) -> Result[int, CliError]:
    """Compose two Results and stop automatically if either one is Err.

    Args:
        dividend: Number to divide.
        divisor: Number to divide by.

    Returns:
        The doubled quotient, or an error when division is impossible.
    """
    first_result: Result[int, CliError]
    if divisor == 0:
        first_result = Err(CliError.INVALID_ARGUMENT_TYPE)
    else:
        first_result = Ok(dividend // divisor)

    # `.q` extracts an Ok value. On Err it jumps to @catch_bubble, so the
    # second operation only runs when the first operation succeeded.
    quotient = first_result.q
    second_result: Result[int, CliError] = Ok(quotient * 2)
    return Ok(second_result.q)


@catch_nothing
def first_character(text: str) -> Option[str]:
    """Propagate an absent optional character with ``Option.q``.

    Args:
        text: Text whose first character should be returned.

    Returns:
        Some containing the first character, or Nothing for empty text.
    """
    possible_character: Option[str] = Some(text[0]) if text else Nothing()
    return Some(possible_character.q)


def explain_with_isinstance(result: Result[int, CliError]) -> str:
    """Handle a Result with a normal branch and explicit type narrowing.

    Args:
        result: Result to inspect.

    Returns:
        A human-readable description of the Result.
    """
    # Use isinstance when you need custom logic in both branches or when a
    # regular if statement is easier to read than structural pattern matching.
    if isinstance(result, Ok):
        return f"isinstance found the value {result.value}"
    return f"isinstance found the error {result.error.name}"


def explain_with_match(result: Result[int, CliError]) -> str:
    """Handle a Result by destructuring its variant with match.

    Args:
        result: Result to inspect.

    Returns:
        A human-readable description of the Result.
    """
    # Use match when variants contain fields you want to unpack, or when the
    # surrounding code already models several distinct cases.
    match result:
        case Ok(value):
            return f"match unpacked the value {value}"
        case Err(error):
            return f"match unpacked the error {error.name}"


def demonstrate_ok() -> None:
    """Show every operation on a successful Result."""
    print("\n=== Ok: a computation succeeded ===")
    result = Ok(21)
    fallback = Err(CliError.INVALID_ARGUMENT_TYPE)

    show("value", result.value)
    show("is_ok()", result.is_ok())
    show("is_err()", result.is_err())
    show("is_ok_and()", result.is_ok_and(lambda value: value > 10))

    # Error predicates and fallback functions are skipped because Ok already
    # has a usable value. This avoids unnecessary or unsafe work.
    show("is_err_and()", result.is_err_and(lambda _error: True))
    show("unwrap()", result.unwrap())
    show("expect()", result.expect("ignored for Ok"))
    show_raised("unwrap_err()", result.unwrap_err)
    show_raised("expect_err()", lambda: result.expect_err("wanted Err"))
    show("unwrap_or()", result.unwrap_or(0))
    show("unwrap_or_else()", result.unwrap_or_else(lambda _error: 0))

    # `map` changes a success value, while `map_err` leaves an Ok untouched.
    show("map()", result.map(lambda value: value * 2))
    show(
        "map_err()",
        result.map_err(lambda _error: CliError.UNKNOWN_ARGUMENT),
    )

    inspected: list[int] = []
    show("inspect()", result.inspect(inspected.append))
    show("inspect side effect", inspected)
    show("inspect_err()", result.inspect_err(lambda error: print(error)))

    # `and` continues with the next Result; `or` keeps this successful one.
    show("and_()", result.and_(fallback))
    show("and_then()", result.and_then(lambda value: Ok(value + 1)))
    show("or_()", result.or_(fallback))
    show("or_else()", result.or_else(lambda _error: fallback))
    show("ok()", result.ok())
    show("err()", result.err())
    show("iter()", list(result.iter()))
    show("q", result.q)


def demonstrate_which_type_to_use() -> None:
    """Explain when to choose Result or Option."""
    print("\n=== Choosing Result or Option ===")
    print("Option: absence is expected; Some(value) or Nothing() is enough.")
    print("Result: an operation can fail and the caller needs an Err reason.")

    # Looking for a bonus fruit is optional: no fruit is a normal game state.
    bonus_fruit: Option[str] = Nothing()
    show("optional bonus fruit", bonus_fruit)

    # Parsing configuration can fail for different reasons, so preserving the
    # error lets the caller report or recover from the specific problem.
    parsed_lives: Result[int, CliError] = Err(CliError.INVALID_ARGUMENT_TYPE)
    show("configuration parsing", parsed_lives)


def demonstrate_err() -> None:
    """Show failure behavior and composition of two Results."""
    print("\n=== Err: a computation failed ===")
    error = Err(CliError.INVALID_ARGUMENT_TYPE)

    show("error.error", error.error)
    show_raised("unwrap()", error.unwrap)

    # Use `.q` when the current function also returns Result and should stop at
    # the first Err. The decorator catches that propagation at the boundary.
    show("two Results (success)", divide_then_double(12, 3))
    show("two Results (failure)", divide_then_double(12, 0))

    # Use isinstance for a familiar if/else and match when destructuring makes
    # the cases clearer. Both styles explicitly handle Ok and Err here.
    show("isinstance with Ok", explain_with_isinstance(Ok(7)))
    show("isinstance with Err", explain_with_isinstance(error))
    show("match with Ok", explain_with_match(Ok(7)))
    show("match with Err", explain_with_match(error))

    print("\n=== Diagnostic: explain where and why an Err occurred ===")
    diagnostic_error = Err(
        CliError.INVALID_ARGUMENT_TYPE,
        diagnostic=Diagnostic(
            filename="config.example.json",
            line_num=3,
            line_text='  "lives": "three"',
            col_start=11,
            col_end=18,
            help_msg="Use an integer, for example: 3",
        ),
        context_msg="The lives setting must be an integer",
        namespace="config",
    )
    # Call print_diagnostic at a user-facing boundary. Internal helpers should
    # normally return/propagate Err instead of printing the same error twice.
    diagnostic_error.print_diagnostic()


def demonstrate_some() -> None:
    """Show every operation on a present Option."""
    print("\n=== Some: an optional value is present ===")
    option = Some(21)
    absent = Nothing()

    show("value", option.value)
    show("is_some()", option.is_some())
    show("is_none()", option.is_none())
    show("is_some_and()", option.is_some_and(lambda value: value > 10))
    show("unwrap()", option.unwrap())
    show("expect()", option.expect("ignored for Some"))
    show("unwrap_or()", option.unwrap_or(0))
    show("unwrap_or_else()", option.unwrap_or_else(lambda: 0))
    show("map()", option.map(lambda value: value * 2))
    show("inspect()", option.inspect(lambda value: show("inspected", value)))
    show("filter(true)", option.filter(lambda value: value > 10))
    show("filter(false)", option.filter(lambda value: value > 100))
    show("and_()", option.and_(Some("next")))
    show("and_then()", option.and_then(lambda value: Some(value + 1)))
    show("or_()", option.or_(Some(99)))
    show("or_else()", option.or_else(lambda: Some(99)))
    show("xor(Some)", option.xor(Some(99)))
    show("xor(Nothing)", option.xor(absent))
    show("ok_or()", option.ok_or(CliError.MISSING_ARGUMENT_VALUE))
    show(
        "ok_or_else()",
        option.ok_or_else(lambda: CliError.MISSING_ARGUMENT_VALUE),
    )
    show("iter()", list(option.iter()))
    show("q", option.q)


def demonstrate_nothing() -> None:
    """Show every operation on an absent Option."""
    print("\n=== Nothing: an optional value is absent ===")
    option = Nothing()

    show("is_some()", option.is_some())
    show("is_none()", option.is_none())
    show("is_some_and()", option.is_some_and(lambda _value: True))
    show_raised("unwrap()", option.unwrap)
    show_raised("expect()", lambda: option.expect("a value was required"))

    # Unlike Some, Nothing uses fallbacks and skips value transformations.
    show("unwrap_or()", option.unwrap_or(0))
    show("unwrap_or_else()", option.unwrap_or_else(lambda: 42))
    show("map()", option.map(lambda value: value))
    show("inspect()", option.inspect(lambda value: print(value)))
    show("filter()", option.filter(lambda value: bool(value)))
    show("and_()", option.and_(Some("next")))
    show("and_then()", option.and_then(lambda value: Some(value)))
    show("or_()", option.or_(Some(99)))
    show("or_else()", option.or_else(lambda: Some(99)))
    show("xor()", option.xor(Some(99)))
    show("ok_or()", option.ok_or(CliError.MISSING_ARGUMENT_VALUE))
    show(
        "ok_or_else()",
        option.ok_or_else(lambda: CliError.MISSING_ARGUMENT_VALUE),
    )
    show("iter()", list(option.iter()))

    # Calling q directly would raise BubbleUpNothing. The decorated helper
    # turns that internal control flow back into a normal Nothing value.
    show("q through decorator", first_character(""))
    show("q with Some", first_character("Pac-Man"))


def main() -> None:
    """Run the complete Result and Option onboarding tour."""
    demonstrate_which_type_to_use()
    demonstrate_ok()
    demonstrate_err()
    demonstrate_some()
    demonstrate_nothing()


if __name__ == "__main__":
    main()
