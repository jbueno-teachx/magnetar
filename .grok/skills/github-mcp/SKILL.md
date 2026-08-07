---
name: github-mcp
description: >
  Use magnetar's project GitHub MCP (issues, PRs, Actions) with OAuth or PAT.
  Pair with github-auth for git push/fetch. Use when the user asks about GitHub
  issues, pull requests, CI, MCP github tools, /github-mcp, or /mcps for this repo.
metadata:
  short-description: "Magnetar GitHub MCP (issues/PRs/Actions)"
---

# github-mcp — magnetar GitHub tools

Project MCP server name: **`github`**. Tools are namespaced `github__…`.

Config: `.grok/config.toml` → `https://api.githubcopilot.com/mcp/`  
Toolsets: `repos`, `issues`, `pull_requests`, `actions`  
Human setup: `docs/github-mcp.md`  
Default repo: **`jbueno-teachx/magnetar`**

## When to load this vs github-auth

| Job | Use |
|-----|-----|
| List/create issues, read PRs, Actions runs | This skill + MCP `search_tool` / `use_tool` |
| `git push` / `fetch` / commit author / `gh` CLI | User skill **github-auth** (SSH + identity) |
| Both (e.g. open PR then push) | github-auth first for git; MCP or `gh` for the PR API |

MCP OAuth and `gh` tokens are independent. SSH can succeed while MCP/`gh` fail.

## Agent procedure

1. **Discover tools** — `search_tool` query `github` (or a specific verb like `github pull request`). Do not guess tool names.
2. **Call** — `use_tool` with the fully qualified name (`github__list_issues`, etc.) and the schema from step 1.
3. **Scope** — pass `owner=jbueno-teachx`, `repo=magnetar` unless the user names another repo.
4. **Writes** (create/update issue, open/comment/merge PR, edit files on GitHub) — **confirm with the user first**.
5. **If the catalog is empty** — first `/hooks-trust` (project MCP will not start in an untrusted folder), then `/mcps` → select `github` → **`i`** (OAuth), then **`r`**. Do not invent a stdio/`npx` server (Node/Docker are often missing here).
6. **If OAuth is impossible** — point at `docs/github-mcp.md` PAT section. Never `cat` token files or paste PATs into chat.

## Do not

- Commit `.grok` tokens, `mcp_credentials.json`, or `~/teachx/secrets/*`
- Wrap the GitHub URL in `npx mcp-remote`
- Broaden `X-MCP-Toolsets` in `.grok/config.toml` without asking
- Use GitLab MCP patterns from clay (wrong host)

## Quick verify (shell)

```bash
grok mcp list
grok mcp doctor github
```

Expect `github` with `(project)` and a successful handshake after OAuth.
