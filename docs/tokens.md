# Token guide

ChangeAtlas talks to your tracker with a personal access token (PAT) read
from **one environment variable**: `CHANGEATLAS_TOKEN`. It is never accepted
as a command-line flag (flags end up in shell history and process lists)
and never read from a config file.

## Creating an Azure DevOps PAT

1. Go to `dev.azure.com` and sign in.
2. Click **User settings** (top-right avatar) → **Personal access tokens**.
3. Click **New Token**.
4. Set **Scopes** to **Custom defined**, then tick exactly these two —
   nothing else:
   - **Work Items — Read**
   - **Code — Read**
5. Set an **expiry** (don't use "no expiration"). Shorter is better; renew
   when it lapses.
6. Copy the token — ADO only shows it once.

Minimal read-only scopes plus an expiry date are the whole mitigation
strategy here: even if the token leaks, it can only read work items and
code, and only until it expires.

## Setting `CHANGEATLAS_TOKEN`

**Windows (PowerShell)** — current session:
```powershell
$env:CHANGEATLAS_TOKEN = "<your-pat>"
```
Persistent (applies to NEW terminals):
```powershell
setx CHANGEATLAS_TOKEN "<your-pat>"
```

**macOS (zsh)** — current session:
```sh
export CHANGEATLAS_TOKEN="<your-pat>"
```
Persistent:
```sh
echo 'export CHANGEATLAS_TOKEN="<your-pat>"' >> ~/.zshrc && source ~/.zshrc
```

**Linux (bash)** — as macOS with `~/.bashrc`:
```sh
echo 'export CHANGEATLAS_TOKEN="<your-pat>"' >> ~/.bashrc && source ~/.bashrc
```

If `CHANGEATLAS_TOKEN` is unset when ChangeAtlas needs to fetch, it prints a
pointer to this file and the exact session-only command for your OS, then
exits — it never gets partway into an HTTP call first.

## Where this actually stores your token (be honest with yourself)

Neither "persistent" option above is a secret store — read this before
choosing one:

- `setx` writes the value into the **Windows registry**, under your user's
  environment block. Anything with read access to your registry (or your
  user profile backup) can read it back in plaintext.
- Appending to `~/.zshrc` / `~/.bashrc` writes the value into a **plaintext
  dotfile** in your home directory. Anything that can read your home
  directory — including any script you run, any backup tool, and anyone
  with access to your machine — can read it back.

Both are normal, common practice, and fine for a low-privilege, short-lived,
read-only token. The mitigations that make this acceptable: **minimal
scopes** (Work Items Read + Code Read only) and a **short expiry**. Treat the
token as something that will eventually leak, and choose scopes and expiry
accordingly.

If you want better-than-plaintext storage, wrap the token in your OS's
credential store instead of exporting it directly:

- **Windows**: Credential Manager (`cmdkey`, or the `CredentialManager`
  PowerShell module), read into `$env:CHANGEATLAS_TOKEN` at the start of
  your session.
- **macOS**: Keychain (`security add-generic-password` /
  `security find-generic-password`).
- **Linux**: `secret-tool` (part of `libsecret`), or your distro's keyring.

These are optional — plain `setx`/`export` is the documented, supported
path. Credential-store wrappers are for anyone who wants to go further.

## What leaves your machine

Nothing except calls to **your own tracker**, authenticated with your own
token. ChangeAtlas never phones home and never calls any third-party
service on your behalf.

The files ChangeAtlas writes — `out/release-<label>-data.json` and the
rendered `out/impact-<label>.html` — contain work item and PR **titles and
URLs only**. The token itself is never written to either file, never logged,
and never embedded in the HTML output. Treat the cache and HTML as shareable
within whatever audience already has read access to those titles and URLs
in your tracker.

## Scope matrix (future gatherers)

Azure DevOps is the only tracker ChangeAtlas gathers from out of the box
today (see `docs/release-data-schema.md` for how any other tracker plugs
in via `out/release-<label>-data.json`, and `prompts/build-gatherer.md` for
writing one). When a contributed gatherer adds a new tracker, its scope
requirements belong in the table below — a contributed gatherer isn't
complete without a row here (see `CONTRIBUTING.md`).

| Tracker | Env var | Minimal scopes | Notes |
|---|---|---|---|
| Azure DevOps | `CHANGEATLAS_TOKEN` | Work Items (Read), Code (Read) | Same product for tracker + git host — one token covers both. |
| _(yours here)_ | | | Jira/GitHub-style setups need **two** tokens — see the "two credentials" note in `prompts/build-gatherer.md`. |
