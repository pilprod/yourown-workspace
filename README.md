# YourOwn Workspace

A public development workspace for YourOwn Platform and its shared agent context. Git submodules pin the platform and context pack to independently published commits.

GitLab is the canonical source for development. The [GitHub repository](https://github.com/pilprod/yourown-workspace) is a mirror. Submit changes and open merge requests on GitLab.

## Repositories

| Repository | Responsibility |
| --- | --- |
| [yourown-workspace](https://gitlab.com/pilprod/yourown-workspace) | Workspace setup, repository map, agent entry points and local readiness checks. |
| [yourown-platform](https://gitlab.com/pilprod/yourown-platform) | Reusable cloud and bare-metal infrastructure definitions and platform Helm. See its own implementation status for delivered capabilities. |
| [yourown-rag](https://gitlab.com/pilprod/yourown-rag) | Shared engineering rules, task skills and curated knowledge sources. |

Agent implementations, product services, MCP servers, custom upstream forks and real environment values belong in separate repositories. Private repositories are optional local additions, not required submodules of this public workspace.

## Quick start

For a new workspace on macOS or Linux, with Git, Bash and Make installed:

```sh
mkdir -p "$HOME/Projects"
git clone --recurse-submodules https://gitlab.com/pilprod/yourown-workspace.git "$HOME/Projects/yourown-workspace"
cd "$HOME/Projects/yourown-workspace"
make prepare
make context-check
```

Open the workspace root in your IDE, or open `yourown.code-workspace` in VS Code. Start your agent from the root after preparation. The checkout directory can have any name; the maintainer's existing checkout can remain named `yourown`.

`make prepare` connects Codex and Claude Code skills by default. Choose `AGENT=codex`, `AGENT=claude` or `AGENT=generic` for just one integration. Preparation initializes missing submodules at their recorded commits and connects local skill directories. It never switches an existing child checkout, discards edits, installs tools, accesses cloud credentials or deploys infrastructure.

Existing local changes and commits differing from the recorded pin are reported and preserved. A successful development readiness check is not a claim that the checkout exactly reproduces the published pins. For a clean reproducible checkout, run `make verify-pins`.

## Agent context

- `AGENTS.md` routes mandatory rules, task skills and repository documentation.
- `CLAUDE.md` imports shared entry instructions and core rules.
- `.agents/skills/` and `.claude/skills/` are local bindings into the pinned RAG pack, created by preparation and ignored by Git.
- The Cursor adapter routes to the same source files.
- API-based runners, including runners using vLLM, must explicitly load rules and selected skills and supply retrieved evidence to the model. `AGENT=generic` checks file availability; it does not implement a model runner.

The initial context pack contains reviewed Markdown and a Terraform skill. Semantic retrieval, vector storage, model adapters and migration of the platform's existing context-bundle tool are follow-up work. The platform may still contain its earlier context implementation during migration; keep following its local entry instructions when editing it.

When opening a submodule alone, follow its own instructions. Do not assume every client discovers the parent's files across a Git repository boundary. The supported shared setup starts from the workspace root.

## Work on a submodule

New submodule checkouts normally have detached HEAD. Create or select an appropriate branch inside the child before making commits. Develop and validate there, publish that child commit, then explicitly stage its path and commit the updated gitlink in this parent repository. The gitlink records the child commit; `.gitmodules` records its URL and path.

The relative sibling URLs in `.gitmodules` resolve against the workspace origin: a GitLab clone uses the GitLab submodules, and a GitHub clone uses the GitHub mirrors. Keep the same repository names and namespace on both hosts. The host does not change the immutable commit recorded by each gitlink; publish the child commit to GitLab and verify its availability in the GitHub mirror before publishing an updated workspace pin. See [Git's submodule URL rules](https://git-scm.com/docs/gitmodules).

Do not use automatic `--remote` updates for preparation. Advance pins as reviewed changes. Avoid broad staging in a workspace that also contains unrelated checkouts.

## Checks

Python 3 is needed for the integration tests; preparation itself uses Git and Bash.

```sh
make check          # bootstrap tests and local context readiness
make verify-pins    # additionally require clean submodules at the recorded commits
```

Tests create disposable local Git fixtures under ignored `.local/`. Workspace checks do not run Terraform or Helm and do not validate the platform's infrastructure. Run the target repository's documented checks for infrastructure changes.

The root ignore rules keep unrelated sibling clones and local configuration out of the parent repository. Publish only the explicitly reviewed workspace files and public submodule references.
