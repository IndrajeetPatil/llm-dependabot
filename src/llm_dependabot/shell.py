"""Logging, failing, and running external commands."""

import datetime as dt
import json
import subprocess
from typing import TYPE_CHECKING, NoReturn

import typer

if TYPE_CHECKING:
    from pathlib import Path


def local_today() -> dt.date:
    """Today's date in the local time zone."""
    return dt.datetime.now().astimezone().date()


def log(message: str) -> None:
    """Print a timestamped line, which the dashboard reads back."""
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def fail(message: str) -> NoReturn:
    """Print an error and exit with status 1."""
    typer.secho(message, err=True, fg="red")
    raise typer.Exit(1)


def sh(*args: str | Path, cwd: Path | None = None, check: bool = True) -> str:
    """Run a command and return its stripped standard output."""
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=check,
    )
    return result.stdout.strip()


def succeeds(*args: str | Path, timeout: float = 120) -> bool:
    """Whether a command exits successfully within the timeout."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError, subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def interactive(*args: str) -> int:
    """Run a command attached to the terminal, so it can prompt the user."""
    return subprocess.run(args, check=False).returncode


def notify(title: str, message: str) -> None:
    """Show a macOS notification."""
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
