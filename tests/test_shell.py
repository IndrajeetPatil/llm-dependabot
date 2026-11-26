"""Tests for logging, failing, and running external commands."""

import io
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
import typer

from llm_dependabot.shell import fail, interactive, log, notify, sh, succeeds

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.conftest import FakeCommands, Spy


def test_log_timestamps_each_line(capsys: pytest.CaptureFixture[str]) -> None:
    """Log lines carry the timestamp the dashboard parses."""
    log("hello")
    assert capsys.readouterr().out.endswith("] hello\n")


def test_log_flushes_each_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each line reaches a buffered log file at once, so a crash loses nothing."""
    log_file = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(log_file, encoding="utf-8"))
    log("hello")
    assert log_file.getvalue().endswith(b"] hello\n")


def test_fail_prints_in_red(spy: Callable[[Any, str], Spy]) -> None:
    """A failure stands out in red on a terminal."""
    secho = spy(typer, "secho")
    with pytest.raises(typer.Exit):
        fail("broken")
    assert secho.calls == [(("broken",), {"err": True, "fg": "red"})]


def test_fail_exits_with_the_message(capsys: pytest.CaptureFixture[str]) -> None:
    """A failure prints to stderr and exits with status 1."""
    with pytest.raises(typer.Exit) as exit_info:
        fail("broken")
    assert exit_info.value.exit_code == 1
    assert capsys.readouterr().err == "broken\n"


def test_sh_returns_stripped_output(commands: FakeCommands) -> None:
    """A command's output comes back without surrounding whitespace."""
    commands.on("tool", stdout="  value \n")
    assert sh("tool", "arg") == "value"
    assert commands.calls("tool") == [["arg"]]


def test_sh_runs_in_the_directory(tmp_path: Path) -> None:
    """A command runs in the requested working directory."""
    cwd = sh(sys.executable, "-c", "import os; print(os.getcwd())", cwd=tmp_path)
    assert cwd == str(tmp_path.resolve())


def test_sh_raises_on_failure_by_default(commands: FakeCommands) -> None:
    """A failing command raises unless the caller opts out."""
    commands.on("tool", stdout="partial", code=1)
    with pytest.raises(subprocess.CalledProcessError):
        sh("tool")
    assert sh("tool", check=False) == "partial"


def test_sh_options(spy: Callable[[Any, str], Spy], commands: FakeCommands) -> None:
    """Commands read no input and decode their output as UTF-8."""
    commands.install("tool")
    run = spy(subprocess, "run")
    sh("tool", check=False)
    assert run.calls == [
        (
            (("tool",),),
            {
                "cwd": None,
                "capture_output": True,
                "encoding": "utf-8",
                "stdin": subprocess.DEVNULL,
                "check": False,
            },
        ),
    ]


def test_succeeds_options(
    spy: Callable[[Any, str], Spy],
    commands: FakeCommands,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A probe reads no input, prints nothing, and waits two minutes by default."""
    commands.on("tool", stdout="noise")
    run = spy(subprocess, "run")
    assert succeeds("tool")
    assert run.calls == [
        (
            (("tool",),),
            {
                "capture_output": True,
                "stdin": subprocess.DEVNULL,
                "timeout": 120,
                "check": False,
            },
        ),
    ]
    assert not capfd.readouterr().out


@pytest.mark.parametrize(
    ("command", "rule", "timeout", "expected"),
    [
        pytest.param("tool", {"code": 0}, 120, True, id="success"),
        pytest.param("tool", {"code": 1}, 120, False, id="failure"),
        pytest.param("tool", {"sleep": 5}, 0.2, False, id="timeout"),
        pytest.param("missing", None, 120, False, id="not installed"),
    ],
)
def test_succeeds(
    commands: FakeCommands,
    command: str,
    rule: dict[str, float] | None,
    timeout: float,
    *,
    expected: bool,
) -> None:
    """Only a command that exists and exits zero within the timeout succeeds."""
    if rule is not None:
        commands.on(command, code=int(rule.get("code", 0)), sleep=rule.get("sleep", 0))
    assert succeeds(command, timeout=timeout) is expected


def test_interactive_returns_the_exit_code(commands: FakeCommands) -> None:
    """An interactive command's exit code comes back."""
    commands.on("tool", code=4)
    assert interactive("tool", "login") == 4


def test_interactive_options(
    spy: Callable[[Any, str], Spy],
    commands: FakeCommands,
) -> None:
    """An interactive command inherits the terminal and never raises."""
    commands.on("tool", code=1)
    run = spy(subprocess, "run")
    assert interactive("tool") == 1
    assert run.calls == [((("tool",),), {"check": False})]


def test_notify_escapes_the_message(commands: FakeCommands) -> None:
    """Notifications quote their text for AppleScript."""
    commands.install("osascript")
    notify("Title", 'say "hi"')
    [[flag, script]] = commands.calls("osascript")
    assert flag == "-e"
    assert script == 'display notification "say \\"hi\\"" with title "Title"'


def test_notify_options(
    spy: Callable[[Any, str], Spy],
    commands: FakeCommands,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A failed notification neither raises nor prints."""
    commands.on("osascript", stdout="noise", code=1)
    run = spy(subprocess, "run")
    notify("Title", "message")
    [(_, options)] = run.calls
    assert options == {"check": False, "capture_output": True}
    assert not capfd.readouterr().out
