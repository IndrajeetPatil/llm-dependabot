"""Logging, failing, and running external commands."""

import datetime as dt
import json
import subprocess
from typing import TYPE_CHECKING, NoReturn

import typer

if TYPE_CHECKING:
    from pathlib import Path


def local_today() -> dt.date:
    return dt.datetime.now().astimezone().date()


def log(message: str) -> None:
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def fail(message: str) -> NoReturn:
    typer.secho(message, err=True, fg="red")
    raise typer.Exit(1)


def sh(*args: str | Path, cwd: Path | None = None, check: bool = True) -> str:
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
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
