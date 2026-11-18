# Configuration

Two YAML files sit next to the script, and every command reads both. Both are
validated on load, so a typo fails with a clear message instead of a silent
misconfiguration.

| File | Committed | Contents |
| --- | --- | --- |
| [`config.yaml`](../config.yaml) | yes | Owner, prompt path, clone directory, timeouts, and the schedule |
| `private.yaml` | no (git-ignored) | Private repositories to include, by name |

Run `make install` after editing either file.

## `config.yaml`

| Key | Meaning |
| --- | --- |
| `owner` | GitHub account whose repositories are considered |
| `prompt_path` | Path of the prompt inside each repository |
| `clone_root` | Where existing clones are found and missing ones are cloned |
| `agent_timeout_hours` | Upper bound for one repository's agent run |
| `cleanup_interval_hours` | How often finished pull requests are cleaned up |
| `groups` | The weekly schedule (see below) |

## Groups and the schedule

Each group runs once a week at a local wall-clock time:

```yaml
groups:
  - name: python
    languages: [Python]
    weekday: Wednesday
    time: "14:30"
```

A repository joins the first group whose `languages` include its GitHub
primary language. The group with `languages: ["*"]` takes everything else.
The default schedule:

| Group | Languages | When |
| --- | --- | --- |
| `r` | R | Monday 11:00 |
| `workflows` | anything not matched by another group | Tuesday 11:00 |
| `python` | Python | Wednesday 14:30 |
| `web` | TypeScript, JavaScript, Astro, Svelte, Vue, HTML, and CSS | Thursday 11:00 |

## Which repositories take part

- **Public:** every non-archived, non-fork public repository owned by `owner`
  that contains the prompt, found automatically at run time.

- **Private:** only those listed in `private.yaml`, so their names never reach
  version control. Each still needs the prompt.

A repository that gains the prompt joins its group the following week.
`make list` shows the current assignment.

## `private.yaml`

`make setup` writes it for you. To edit it by hand, copy
[`private.example.yaml`](../private.example.yaml):

```yaml
repos:
  - my-private-app
  - another-private-tool
```

Without `private.yaml`, only public repositories run. A git hook rejects any
commit that adds this file or names one of its repositories.
