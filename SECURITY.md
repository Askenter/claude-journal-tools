# Security model

These tools install **hooks that run on every Claude Code session exit** and
**push the contents of your sessions to a git repository**. Read this before
installing the plugin or pointing it at a repo.

## What gets pushed, and where

On each `Stop` event the hook writes two artifacts to your **data repo**
(the `claude-journal` clone, *not* this tools repo):

- a structural breadcrumb JSON (`raw/<device>/<date>/<session_id>.json`)
- a tail-truncated transcript (`<session_id>.transcript.md`)

then `git commit && git push`. The transcript can contain anything that was
in your session — prompts, file contents, command output. **Treat the data
repo as containing your raw working material.**

## Secret handling in pushed text

Secrets are kept out of the journal by **three layers**, strongest first:

1. **Tool input/output is dropped entirely.** The transcript keeps only
   user/assistant *prose* — every `tool_use` and `tool_result` block (command
   output, file reads, env dumps, where secrets most often appear) is discarded
   before anything is written (`transcript.py`).
2. **Pattern redaction over the remaining prose.** A shared scrubber
   (`tools/journal/redaction.py`) replaces known key shapes with `[REDACTED]`
   in both transcripts and the captured `CLAUDE.md` snapshots: Anthropic/OpenAI
   `sk-…`, Stripe `sk_/rk_…`, the GitHub token family (`ghp_/gho_/ghu_/ghs_/ghr_`
   and `github_pat_`), Google `AIza…` and `GOCSPX-…`, AWS access-key ids and
   labelled secret keys, Slack tokens and webhook URLs, `Authorization: Bearer`
   tokens, database URIs with embedded credentials, JWTs, PEM private-key
   blocks, and the base64 git-crypt key prefix.
3. **Encryption at rest.** Everything under `raw/` and `state/` is
   git-crypt-encrypted in the repo (see "Encryption" below), so even content
   that slips past layers 1–2 is ciphertext on your git host.

**This is defense-in-depth, not a guarantee.** Layer 2 is pattern-based: it
matches *known* secret formats and will miss novel or unusual ones, and the
breadcrumb's `first_prompt` field is truncated but not pattern-scrubbed. The
load-bearing protection is layer 3 — keep the data repo **private and
git-crypt-encrypted** and the git-crypt key off the repo. Don't rely on
redaction alone, and don't paste a credential you couldn't tolerate sitting
encrypted in your own repo.

### Requirements you are responsible for

1. **The data repo MUST be private.** Never point these tools at a public
   repository. There is no server-side redaction.
2. **The data repo MUST be encrypted at rest with git-crypt.** The pipeline
   is designed around it (see "Encryption" below). Running without git-crypt
   means plaintext transcripts sit in your git host.
3. **You supply your own data repo.** This tools repo is generic; it does not
   ship a data repo or a key. Set `CLAUDE_JOURNAL_REPO_URL` to *your* private
   clone URL.

## Encryption (git-crypt)

The data repo encrypts these directories at rest:
`raw/`, `digests/`, `memories/`, `skills/`, `proposals/`, `state/`.

- The symmetric key lives **outside** any repo, at
  `~/.claude/journal/git-crypt.key` (`chmod 600`). It is never committed.
- This tools repo contains **no key material** — `tools/journal/encryption.py`
  only *detects* the git-crypt magic-byte prefix to warn when a repo is
  locked; it cannot decrypt anything.
- Transfer the key between devices out-of-band (a password manager), never
  through the repo or a shared log. The Phase 2 consolidator reads it from
  `GIT_CRYPT_KEY_B64` in its environment — keep that value secret.

## Failure behavior

Hooks are best-effort and always exit 0 so they never block your session. A
locked repo, a failed pull, or a failed push degrades gracefully (warnings
surfaced at SessionStart, breadcrumbs buffered locally) rather than losing
data or interrupting you.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository rather than a
public issue.
