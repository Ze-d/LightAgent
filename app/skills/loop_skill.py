"""Loop skill - recurring execution with interval."""
from typing import Any


async def loop(interval: str, command: str, max_rounds: int | None = None) -> str:
    """Set up a recurring task.

    Args:
        interval: Time interval (e.g., "5m", "10s", "1h")
        command: The command or task to run
        max_rounds: Maximum number of iterations (optional)

    Returns:
        Confirmation message with loop details
    """
    if not interval or not command:
        return "Error: interval and command are required."

    valid_units = ["s", "m", "h", "d"]
    unit = interval[-1] if len(interval) > 1 else ""
    if unit not in valid_units:
        return f"Invalid interval unit. Use: {', '.join(valid_units)}"

    try:
        int(interval[:-1]) if unit else int(interval)
    except ValueError:
        return "Invalid interval value."

    rounds_msg = f" up to {max_rounds} rounds" if max_rounds else ""

    return f"""[Skill: loop] Loop scheduled:

- Interval: every {interval}
- Command: {command}
- Rounds: unlimited{rounds_msg}

Use /stop to cancel the loop.

Note: This skill registers the loop but actual execution requires a scheduler."""
