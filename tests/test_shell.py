"""Tests for logging, failing, and running external commands."""

from typing import TYPE_CHECKING

import pytest
import typer

from llm_dependabot.shell import fail, interactive, log, notify, sh, succeeds

if TYPE_CHECKING:
    from tests.conftest import FakeCommands


def test_log_timestamps_each_line(capsys: pytest.CaptureFixture[str]) -> None:
    """Log lines carry the timestamp the dashboard parses."""
    log("hello")
    assert capsys.readouterr().out.endswith("] hello\n")


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


def test_notify_escapes_the_message(commands: FakeCommands) -> None:
    """Notifications quote their text for AppleScript."""
    commands.install("osascript")
    notify("Title", 'say "hi"')
    [[flag, script]] = commands.calls("osascript")
    assert flag == "-e"
    assert script == 'display notification "say \\"hi\\"" with title "Title"'
