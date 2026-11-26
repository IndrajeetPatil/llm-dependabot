"""Tests for the interactive setup steps, with answers and commands scripted."""

from typing import TYPE_CHECKING, Any, NamedTuple

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


class Terminal:
    """Scripted replies to setup's questions, and a transcript of the session.

    Fails on any unexpected question.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stand in for typer's output, confirm, and prompt."""
        self.replies: list[bool] = []
        self.transcript: list[tuple[Any, ...]] = []
        for name in ("echo", "secho", "confirm", "prompt"):
            monkeypatch.setattr(setup_wizard.typer, name, getattr(self, name))

    def echo(self, message: str) -> None:
        """Record a line of output."""
        self.transcript.append(("echo", message))

    def secho(self, message: str, **style: object) -> None:
        """Record a styled line of output, such as a heading or an error."""
        self.transcript.append(("secho", message, style))

    def confirm(self, question: str, **options: object) -> bool:
        """Answer the next scripted reply.

        The replies are read, never popped: they may be a parametrised case's
        list, which must stay intact for the next run of the same test.
        """
        self.transcript.append(("confirm", question, options))
        asked = len([entry for entry in self.transcript if entry[0] == "confirm"])
        assert asked <= len(self.replies), f"unexpected question: {question}"
        return self.replies[asked - 1]

    def prompt(self, text: str, **options: object) -> str:
        """Record a press of Enter."""
        self.transcript.append(("prompt", text, options))
        return ""


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> Terminal:
    """Scripted answers to setup's questions, recording everything shown."""
    return Terminal(monkeypatch)


def step(title: str) -> tuple[Any, ...]:
    """A step's heading in the transcript."""
    return ("secho", f"\n==> {title}", {"bold": True})


def error(message: str) -> tuple[Any, ...]:
    """A failure in the transcript."""
    return ("secho", message, {"err": True, "fg": "red"})


def pause(message: str) -> tuple[Any, ...]:
    """A wait for Enter in the transcript."""
    text = f"{message} Press Enter to continue"
    return ("prompt", text, {"default": "", "show_default": False})


def ask(question: str, **options: object) -> tuple[Any, ...]:
    """A yes-or-no question in the transcript, defaulting to yes."""
    return ("confirm", question, options or {"default": True})


@pytest.mark.parametrize("installed", [True, False])
def test_ensure_brew_bundle(
    commands: FakeCommands,
    terminal: Terminal,
    *,
    installed: bool,
) -> None:
    """Setup goes on only once every Brewfile package is installed."""
    commands.on("brew", code=0 if installed else 1)
    if installed:
        ensure_brew_bundle()
    else:
        with pytest.raises(typer.Exit):
            ensure_brew_bundle()
    assert commands.calls("brew") == [
        ["bundle", "check", "--no-upgrade", "--file", str(setup_wizard.BREWFILE)],
    ]
    assert terminal.transcript == [
        step("Homebrew packages (Brewfile)"),
        ("echo", "installed")
        if installed
        else error(
            "some Brewfile packages are missing; run `make setup`, which installs them",
        ),
    ]


def test_ensure_signed_in_offers_gh_login(
    commands: FakeCommands,
    terminal: Terminal,
    config: Config,
) -> None:
    """A signed-out gh gets a login; an agent without a check is trusted."""
    commands.on("gh", "auth status", code=1, times=1)
    commands.install("agent")
    terminal.replies = [True]
    ensure_signed_in(config)
    assert commands.calls("gh") == [
        ["auth", "status"],
        ["auth", "login"],
        ["auth", "status"],
    ]
    assert terminal.transcript == [
        step("GitHub CLI sign-in"),
        ask("gh is not signed in. Run `gh auth login` now?"),
        ("echo", "signed in"),
        step("Test agent sign-in"),
        ("echo", "no sign-in check configured; make sure Test agent is signed in"),
    ]


def test_ensure_signed_in_waits_for_the_agent(
    commands: FakeCommands,
    terminal: Terminal,
    config: Config,
) -> None:
    """Setup waits until the agent's sign-in check passes."""
    commands.install("gh")
    commands.on("agent", "whoami", code=1, times=2)
    config.agent = config.agent.model_copy(update={"check": ["agent", "whoami"]})
    ensure_signed_in(config)
    assert len(commands.calls("agent")) == 3
    failed = (
        "echo",
        "`agent whoami` failed. Run `agent` in another terminal and sign in.",
    )
    waited = pause("Once signed in, come back here.")
    assert terminal.transcript == [
        step("GitHub CLI sign-in"),
        ("echo", "signed in"),
        step("Test agent sign-in"),
        failed,
        waited,
        failed,
        waited,
        ("echo", "signed in"),
    ]


def test_setup_stops_if_gh_stays_signed_out(
    commands: FakeCommands,
    terminal: Terminal,
    config: Config,
) -> None:
    """Declining to sign gh in stops setup."""
    commands.on("gh", code=1)
    commands.install("agent")
    terminal.replies = [False]
    with pytest.raises(typer.Exit):
        ensure_signed_in(config)
    assert commands.calls("gh") == [["auth", "status"]]
    assert terminal.transcript[-1] == error("gh must be signed in")


def test_setup_stops_without_the_agent(
    commands: FakeCommands,
    terminal: Terminal,
    config: Config,
) -> None:
    """A missing agent command stops setup, pointing at the Brewfile."""
    commands.install("gh")
    with pytest.raises(typer.Exit):
        ensure_signed_in(config)
    assert terminal.transcript[-1] == error(
        "agent is not installed; add its package to the Brewfile"
        " and rerun `make setup`",
    )


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
    terminal: Terminal,
    config: Config,
    case: OwnerCase,
) -> None:
    """The owner can follow the signed-in account, in config.yaml too.

    Only the first top-level owner line changes.
    """
    setup_wizard.CONFIG_FILE.write_text(
        "# comment\nowner: octo\nother: owner: x\n---\nowner: octo\n",
    )
    commands.on("gh", "api user", stdout=f"{case.login}\n")
    terminal.replies = case.replies
    check_owner(config)
    assert config.owner == case.owner
    assert setup_wizard.CONFIG_FILE.read_text() == (
        f"# comment\nowner: {case.owner}\nother: owner: x\n---\nowner: octo\n"
    )
    assert commands.calls("gh") == [["api", "user", "--jq", ".login"]]
    if case.login == "OCTO":
        shown = [("echo", "config.yaml owner 'octo' matches your account")]
    else:
        shown = [
            ("echo", "config.yaml names 'octo', but gh is signed in as 'hubot'."),
            ask("Set owner to 'hubot' in config.yaml?"),
        ]
    assert terminal.transcript == [step("Repository owner"), *shown]


@pytest.mark.parametrize(
    ("exists", "replies", "created"),
    [
        pytest.param(True, [], True, id="already there"),
        pytest.param(False, [True], True, id="created on request"),
        pytest.param(False, [False], False, id="refused"),
    ],
)
def test_ensure_clone_root(
    terminal: Terminal,
    config: Config,
    replies: list[bool],
    *,
    exists: bool,
    created: bool,
) -> None:
    """A missing clone root is created, with its parents, only if the user agrees."""
    root = config.clone_root / "nested/clones"
    config.clone_root = root
    if exists:
        root.mkdir(parents=True)
    terminal.replies = replies
    if created:
        ensure_clone_root(config)
    else:
        with pytest.raises(typer.Exit):
            ensure_clone_root(config)
    assert root.is_dir() is created
    question = [ask(f"{root} does not exist. Create it?")] if replies else []
    outcome = (
        ("echo", str(root))
        if created
        else error("set clone_root in config.yaml to an existing directory")
    )
    assert terminal.transcript == [step("Clone directory"), *question, outcome]


@pytest.fixture
def private_listing(monkeypatch: pytest.MonkeyPatch, config: Config) -> None:
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

    def owned_repos(listed_for: Config, visibility: str) -> list[GitHubRepo]:
        """The private repositories of the configured owner."""
        assert (listed_for, visibility) == (config, "private")
        return listing

    def prompts_in(repo: Repo, looked_up_for: Config) -> tuple[str, ...]:
        """The update-deps prompt, for the repositories that carry one."""
        assert looked_up_for is config
        return ("update-deps",) if repo.name in with_prompts else ()

    monkeypatch.setattr(setup_wizard, "owned_repos", owned_repos)
    monkeypatch.setattr(setup_wizard, "prompts_in", prompts_in)


HEADER = "# Private repositories to include; git-ignored, never commit it.\n\n"


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
    terminal: Terminal,
    config: Config,
    existing: str | None,
    replies: list[bool],
    chosen: list[str],
) -> None:
    """Only private repositories with prompts are offered, one question each."""
    if existing is not None:
        setup_wizard.PRIVATE_FILE.write_text(existing)
        config.private_repos = frozenset({"old"})
    terminal.replies = replies
    choose_private_repos(config)
    written = setup_wizard.PRIVATE_FILE.read_text()
    if existing is None or replies[0]:
        assert written == HEADER + yaml.safe_dump({"repos": chosen})
    assert config.private_repos == frozenset(chosen)
    redo = [
        ("echo", "private.yaml already lists 1 repositories"),
        ("confirm", "Choose them again (rewrites private.yaml)?", {}),
    ]
    offers = [
        ask("Include private repository alpha?"),
        ask("Include private repository gamma?"),
        ("echo", f"wrote private.yaml with {len(chosen)} repositories"),
    ]
    expected = [step("Private repositories")]
    if existing is not None:
        expected += redo
    if existing is None or replies[0]:
        expected += offers
    assert terminal.transcript == expected


def test_choose_private_repos_without_candidates(
    terminal: Terminal,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no private repository carrying a prompt, an empty list is written."""
    monkeypatch.setattr(setup_wizard, "owned_repos", lambda _config, _v: [])
    choose_private_repos(config)
    assert setup_wizard.PRIVATE_FILE.read_text() == HEADER + "repos: []\n"
    assert terminal.transcript == [
        step("Private repositories"),
        ("echo", "no private repositories contain any of the configured prompts"),
        ("echo", "wrote private.yaml with 0 repositories"),
    ]


@pytest.mark.parametrize("code", [0, 1])
def test_install_git_hooks(
    commands: FakeCommands,
    terminal: Terminal,
    code: int,
) -> None:
    """Prek installs the hooks, and a failure stops setup."""
    commands.on("prek", code=code)
    if code == 0:
        install_git_hooks()
    else:
        with pytest.raises(typer.Exit):
            install_git_hooks()
    assert commands.calls("prek") == [["install"]]
    failed = [error("prek install failed")] if code else []
    assert terminal.transcript == [step("Git hooks"), *failed]


def test_ensure_full_disk_access_waits_for_the_grant(
    terminal: Terminal,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After installing, setup shows the steps until the grant takes effect."""
    grants = [False, False, True]
    events: list[str] = []

    def install_agents(installed_for: Config) -> None:
        """Record the install."""
        assert installed_for is config
        events.append("install")

    def full_disk_access_granted(checked_for: Config) -> bool:
        """The next scripted answer."""
        assert checked_for is config
        return grants.pop(0)

    monkeypatch.setattr(setup_wizard, "install_agents", install_agents)
    monkeypatch.setattr(
        setup_wizard,
        "full_disk_access_granted",
        full_disk_access_granted,
    )
    monkeypatch.setattr(
        setup_wizard,
        "show_full_disk_access_steps",
        lambda: events.append("steps"),
    )
    ensure_full_disk_access(config)
    assert events == ["install", "steps", "steps"]
    waited = pause("Once LLM Dependabot is switched on,")
    assert terminal.transcript == [
        step("LLM Dependabot app, launchd agents, and Full Disk Access"),
        waited,
        waited,
        ("echo", f"scheduled jobs can read {config.clone_root}"),
    ]


def test_run_setup_runs_every_step_in_order(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup checks prerequisites first and installs the agents last."""
    steps = {
        "ensure_brew_bundle": (),
        "ensure_signed_in": (config,),
        "check_owner": (config,),
        "ensure_clone_root": (config,),
        "choose_private_repos": (config,),
        "install_git_hooks": (),
        "ensure_full_disk_access": (config,),
    }
    ran: list[tuple[str, tuple[object, ...]]] = []
    for name in steps:
        monkeypatch.setattr(
            setup_wizard,
            name,
            lambda *args, name=name: ran.append((name, args)),
        )
    run_setup(config)
    assert ran == list(steps.items())
