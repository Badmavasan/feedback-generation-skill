"""Characteristic definitions and validation."""
from enum import Enum


class Characteristic(str, Enum):
    LOGOS = "logos"
    TECHNICAL = "technical"
    ERROR_POINTED = "error_pointed"
    EXAMPLE_UNRELATED = "with_example_unrelated_to_exercise"
    EXAMPLE_RELATED = "with_example_related_to_exercise"


ALL_CHARACTERISTICS = [c.value for c in Characteristic]

# Image feedback is always with_example_related_to_exercise —
# an annotated image is by definition a concrete exercise-anchored illustration.
IMAGE_CAPABLE = {
    Characteristic.EXAMPLE_RELATED.value,
}

# Characteristics that require error context
ERROR_REQUIRED = {Characteristic.ERROR_POINTED.value}

# Characteristics that require exercise context
EXERCISE_REQUIRED = {Characteristic.EXAMPLE_RELATED.value}

# Characteristics incompatible with task_type level (no exercise, no error context)
TASK_TYPE_INCOMPATIBLE = {
    Characteristic.ERROR_POINTED.value,
    Characteristic.EXAMPLE_RELATED.value,
}

# Characteristics incompatible with exercise level (no error context)
EXERCISE_LEVEL_INCOMPATIBLE = {
    Characteristic.ERROR_POINTED.value,
}

# Characteristics incompatible with error level (no exercise context)
ERROR_LEVEL_INCOMPATIBLE = {
    Characteristic.EXAMPLE_RELATED.value,
}


class OfflineLevel(str, Enum):
    TASK_TYPE = "task_type"        # KC only — no exercise, no error
    EXERCISE = "exercise"          # KC + exercise (description + solutions)
    ERROR = "error"                # KC + error (tag + description)
    ERROR_EXERCISE = "error_exercise"  # KC + error + exercise


def validate_characteristics(
    characteristics: list[str],
    level: str,
    has_exercise: bool,
    has_error: bool,
) -> list[str]:
    """
    Validate and return cleaned characteristics list.
    Raises ValueError if requirements are not met.
    """
    unknown = [c for c in characteristics if c not in ALL_CHARACTERISTICS]
    if unknown:
        raise ValueError(f"Unknown characteristics: {unknown}")

    for c in characteristics:
        if c in ERROR_REQUIRED and not has_error:
            raise ValueError(
                f"Characteristic '{c}' requires error context (tag + description)"
            )
        if c in EXERCISE_REQUIRED and not has_exercise:
            raise ValueError(
                f"Characteristic '{c}' requires exercise context"
            )

    return characteristics


def validate_for_level(characteristics: list[str], level: str) -> list[str]:
    """
    Validate characteristics against a fixed level.
    Raises ValueError naming the invalid combination.
    """
    unknown = [c for c in characteristics if c not in ALL_CHARACTERISTICS]
    if unknown:
        raise ValueError(f"Unknown characteristics: {unknown}")

    if level == OfflineLevel.TASK_TYPE:
        invalid = [c for c in characteristics if c in TASK_TYPE_INCOMPATIBLE]
        if invalid:
            raise ValueError(
                f"Characteristics {invalid} are not compatible with task_type level. "
                f"task_type has no exercise or error context. "
                f"Allowed: logos, technical, with_example_unrelated_to_exercise."
            )

    elif level == OfflineLevel.EXERCISE:
        invalid = [c for c in characteristics if c in EXERCISE_LEVEL_INCOMPATIBLE]
        if invalid:
            raise ValueError(
                f"Characteristics {invalid} are not compatible with exercise level. "
                f"exercise level has no error context — use error or error_exercise level for error_pointed."
            )

    elif level == OfflineLevel.ERROR:
        invalid = [c for c in characteristics if c in ERROR_LEVEL_INCOMPATIBLE]
        if invalid:
            raise ValueError(
                f"Characteristics {invalid} are not compatible with error level. "
                f"error level has no exercise context — use error_exercise level if you need both."
            )

    return characteristics
