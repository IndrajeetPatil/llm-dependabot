"""Tests for the interactive setup steps, with answers and commands scripted."""

from typing import TYPE_CHECKING, NamedTuple

import pytest
import typer
import yaml

from llm_dependabot import setup_wizard
from llm_dependabot.github import GitHubRepo
from llm_dependabot.setup_wizard import (
    check_owner,
    choose_private_repos,
    ensure_brew_bundle,
    ensure_clone_root,
    ensure_full_disk_access,
    ensure_signed_in,
    install_git_hooks,
    run_setup,
)

if TYPE_CHECKING:
    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo
    from tests.conftest import FakeCommands


class Answers:
    """Scripted replies to setup's questions, failing on any unexpected one."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stand in for typer's confirm and prompt."""
        self.replies: list[bool] = []
        self.questions: list[str] = []
        self.pauses: int = 0
        monkeypatch.setattr(setup_wizard.typer, "confirm", self.confirm)
        monkeypatch.setattr(setup_wizard.typer, "prompt", self.prompt)

    def confirm(self, question: str, *, default: bool = False) -> bool:
        """Answer the next scripted reply.

        The replies are read, never popped: they may be a parametrised case's
        list, which must stay intact for the next run of the same test.
        """
        del default
        self.questions.append(question)
        asked = len(self.questions)
        assert asked <= len(self.replies), f"unexpected question: {question}"
        return self.replies[asked - 1]

    def prompt(self, _text: str, **_kwargs: object) -> str:
        """Count a press of Enter."""
        self.pauses += 1
        return ""


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> Answers:
    """Scripted answers to setup's questions."""
    return Answers(monkeypatch)


@pytest.mark.parametrize("installed", [True, False])
def test_ensure_brew_bundle(commands: FakeCommands, *, installed: bool) -> None:
    """Setup goes on only once every Brewfile package is installed."""
    commands.on("brew", code=0 if installed else 1)
    if installed:
        ensure_brew_bundle()
    else:
        with pytest.raises(typer.Exit):
            ensure_brew_bundle()
    [call] = commands.calls("brew")
    assert call[:3] == ["bundle", "check", "--no-upgrade"]


def test_ensure_signed_in_offers_gh_login(
    commands: FakeCommands,
    answers: Answers,
    config: Config,
) -> None:
    """A signed-out gh gets a login; an agent without a check is trusted."""
    commands.on("gh", "auth status", code=1, times=1)
    commands.install("agent")
    answers.replies = [True]
    ensure_signed_in(config)
    assert commands.calls("gh") == [
        ["auth", "status"],
        ["auth", "login"],
        ["auth", "status"],
    ]


def test_ensure_signed_in_waits_for_the_agent(
    commands: FakeCommands,
    answers: Answers,
    config: Config,
) -> None:
    """Setup waits until the agent's sign-in check passes."""
    commands.install("gh")
    commands.on("agent", "whoami", code=1, times=2)
    config.agent = config.agent.model_copy(update={"check": ["agent", "whoami"]})
    ensure_signed_in(config)
    assert answers.pauses == 2
    assert len(commands.calls("agent")) == 3


def test_setup_stops_if_gh_stays_signed_out(
    commands: FakeCommands,
    answers: Answers,
    config: Config,
) -> None:
    """Declining to sign gh in stops setup."""
    commands.on("gh", code=1)
    commands.install("agent")
    answers.replies = [False]
    with pytest.raises(typer.Exit):
        ensure_signed_in(config)
    assert commands.calls("gh") == [["auth", "status"]]


def test_setup_stops_without_the_agent(
    commands: FakeCommands,
    config: Config,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing agent command stops setup, pointing at the Brewfile."""
    commands.install("gh")
    with pytest.raises(typer.Exit):
        ensure_signed_in(config)
    assert "agent is not installed" in capsys.readouterr().err


class OwnerCase(NamedTuple):
    """The signed-in account, the user's reply, and the owner that results."""

    login: str
    replies: list[bool]
    owner: str


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(OwnerCase("OCTO", [], "octo"), id="same account, any case"),
        pytest.param(OwnerCase("hubot", [True], "hubot"), id="switch account"),
        pytest.param(OwnerCase("hubot", [False], "octo"), id="keep the owner"),
    ],
)
def test_check_owner(
    commands: FakeCommands,
    answers: Answers,
    config: Config,
    case: OwnerCase,
) -> None:
    """The owner can follow the signed-in account, in config.yaml too."""
    setup_wizard.CONFIG_FILE.write_text("# comment\nowner: octo\nother: owner: x\n")
    commands.on("gh", "api user", stdout=f"{case.login}\n")
    answers.replies = case.replies
    check_owner(config)
    assert config.owner == case.owner
    assert setup_wizard.CONFIG_FILE.read_text() == (
        f"# comment\nowner: {case.owner}\nother: owner: x\n"
    )


@pytest.mark.parametrize(
    ("exists", "replies", "created"),
    [
        pytest.param(True, [], True, id="already there"),
        pytest.param(False, [True], True, id="created on request"),
        pytest.param(False, [False], False, id="refused"),
    ],
)
def test_ensure_clone_root(
    answers: Answers,
    config: Config,
    replies: list[bool],
    *,
    exists: bool,
    created: bool,
) -> None:
    """A missing clone root is created only with the user's agreement."""
    if exists:
        config.clone_root.mkdir(parents=True)
    answers.replies = replies
    if created:
        ensure_clone_root(config)
    else:
        with pytest.raises(typer.Exit):
            ensure_clone_root(config)
    assert config.clone_root.is_dir() is created


@pytest.fixture
def private_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake private repositories, of which the ones named here carry prompts."""
    with_prompts = ["alpha", "gamma"]
    listing = [
        GitHubRepo.model_validate({
            "name": name,
            "visibility": "PRIVATE",
            "primaryLanguage": None,
            "defaultBranchRef": {"name": "main"},
        })
        for name in ("alpha", "beta", "gamma")
    ]
    monkeypatch.setattr(setup_wizard, "owned_repos", lambda _config, _v: listing)

    def prompts_in(repo: Repo, _config: Config) -> tuple[str, ...]:
        """The update-deps prompt, for the repositories that carry one."""
        return ("update-deps",) if repo.name in with_prompts else ()

    monkeypatch.setattr(setup_wizard, "prompts_in", prompts_in)


@pytest.mark.parametrize(
    ("existing", "replies", "chosen"),
    [
        pytest.param(None, [True, False], ["alpha"], id="first choice"),
        pytest.param(
            "repos: [old]\n",
            [True, True, True],
            ["alpha", "gamma"],
            id="redo",
        ),
        pytest.param("repos: [old]\n", [False], ["old"], id="keep the list"),
    ],
)
@pytest.mark.usefixtures("private_listing")
def test_choose_private_repos(
    answers: Answers,
    config: Config,
    existing: str | None,
    replies: list[bool],
    chosen: list[str],
) -> None:
    """Only private repositories with prompts are offered, one question each."""
    if existing is not None:
        setup_wizard.PRIVATE_FILE.write_text(existing)
        config.private_repos = frozenset({"old"})
    answers.replies = replies
    choose_private_repos(config)
    written = yaml.safe_load(setup_wizard.PRIVATE_FILE.read_text())
    assert written == {"repos": chosen}
    assert config.private_repos == frozenset(chosen)
    # beta carries no prompt, so it is never offered.
    assert not any("beta" in question for question in answers.questions)


def test_choose_private_repos_without_candidates(
    answers: Answers,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no private repository carrying a prompt, an empty list is written."""
    monkeypatch.setattr(setup_wizard, "owned_repos", lambda _config, _v: [])
    choose_private_repos(config)
    assert yaml.safe_load(setup_wizard.PRIVATE_FILE.read_text()) == {"repos": []}
    assert "no private repositories" in capsys.readouterr().out
    assert answers.questions == []


@pytest.mark.parametrize("code", [0, 1])
def test_install_git_hooks(commands: FakeCommands, code: int) -> None:
    """Prek installs the hooks, and a failure stops setup."""
    commands.on("prek", code=code)
    if code == 0:
        install_git_hooks()
    else:
        with pytest.raises(typer.Exit):
            install_git_hooks()
    assert commands.calls("prek") == [["install"]]


def test_ensure_full_disk_access_waits_for_the_grant(
    answers: Answers,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After installing, setup shows the steps until the grant takes effect."""
    grants = [False, False, True]
    events: list[str] = []
    monkeypatch.setattr(
        setup_wizard,
        "install_agents",
        lambda _config: events.append("install"),
    )
    monkeypatch.setattr(
        setup_wizard,
        "full_disk_access_granted",
        lambda _config: grants.pop(0),
    )
    monkeypatch.setattr(
        setup_wizard,
        "show_full_disk_access_steps",
        lambda: events.append("steps"),
    )
    ensure_full_disk_access(config)
    assert events == ["install", "steps", "steps"]
    assert answers.pauses == 2


def test_run_setup_runs_every_step_in_order(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup checks prerequisites first and installs the agents last."""
    steps = [
        "ensure_brew_bundle",
        "ensure_signed_in",
        "check_owner",
        "ensure_clone_root",
        "choose_private_repos",
        "install_git_hooks",
        "ensure_full_disk_access",
    ]
    ran: list[str] = []
    for name in steps:
        monkeypatch.setattr(
            setup_wizard,
            name,
            lambda *_args, name=name: ran.append(name),
        )
    run_setup(config)
    assert ran == steps
