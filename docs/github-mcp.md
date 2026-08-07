# How to set up GitHub MCP for magnetar

Magnetar lives on **GitHub** (`jbueno-teachx/magnetar`), not GitLab.  
Grok uses GitHub’s **hosted** MCP over streamable HTTP. No `npx` / Docker required.

| | |
|--|--|
| **Repo** | https://github.com/jbueno-teachx/magnetar |
| **Remote git** | `git@github.com:jbueno-teachx/magnetar.git` |
| **MCP endpoint** | `https://api.githubcopilot.com/mcp/` |
| **Project config** | [`.grok/config.toml`](../.grok/config.toml) |
| **Agent skill** | [`.grok/skills/github-mcp/SKILL.md`](../.grok/skills/github-mcp/SKILL.md) |
| **Git SSH / `gh`** | user skill `~/.grok/skills/github-auth/` |

---

## 1. Trust this folder (required)

Project MCP/LSP/hooks stay **off** until the folder is trusted.  
`grok mcp doctor github` will report `folder untrusted` until you do this.

In the Grok TUI (this session is fine):

```text
/hooks-trust
```

Or launch a new session with `grok --trust` from the repo root.  
The grant is stored in `~/.grok/trusted_folders.toml` (not in git).

---

## 2. Sign in to GitHub MCP (OAuth)

1. Start Grok in this repo.
2. `/mcps` (or Ctrl+L → MCP Servers).
3. Select **github**. Press **`i`** to authenticate.
4. Complete the browser flow. Grok stores tokens in `~/.grok/mcp_credentials.json` (owner-only).
5. Press **`r`** to refresh. Tool count should be non-zero.

Verify from a shell:

```bash
grok mcp list
grok mcp doctor github
grok inspect
```

Expect `github` marked `(project)` and a successful handshake.

---

## 3. PAT alternative (optional)

Use this only if OAuth is blocked. **Never commit the token.**

```bash
# classic or fine-grained PAT with repo + workflow read (write if you want MCP to open PRs)
install -m 600 /dev/null ~/teachx/secrets/github_token.txt
# edit the file with the token; do not echo it into the shell history

export GITHUB_PERSONAL_ACCESS_TOKEN="$(tr -d ' \t\r\n' < ~/teachx/secrets/github_token.txt)"
```

Then either:

- Launch Grok with that env var **and** uncomment the `Authorization` header in `.grok/config.toml`, or
- Keep OAuth and use the same file only for `gh` via `/github-auth`.

`github-auth` still owns **git over SSH**. MCP OAuth and `gh` tokens are independent: SSH can work while `gh` / MCP do not.

---

## 4. What the server is allowed to do

Project config sends:

```text
X-MCP-Toolsets = repos,issues,pull_requests,actions
```

That is enough for repo metadata, issues, PRs, and Actions. Widen the header only when a task needs more (discussions, security, projects, …).

Agents must **confirm** before MCP writes (create/update issue, open/comment PR, merge).

---

## 5. Reload after config edits

`/mcps` → **`r`**, or restart Grok. Project `.grok/config.toml` **replaces** a same-named user-level `github` server entirely (fields are not merged).

---

## 6. Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `grok mcp list` shows nothing | CWD is not the repo root, or folder is untrusted |
| Server listed, 0 tools | Press `i` in `/mcps`; check `~/.grok/logs/` |
| OAuth loop / Copilot policy | Use the PAT header path above |
| `gh` invalid token, git push works | Expected until `~/teachx/secrets/github_token.txt` exists; SSH ≠ MCP |
| Want to turn it off locally | `grok mcp disable github` (writes user enable-state, does not edit this file) |
