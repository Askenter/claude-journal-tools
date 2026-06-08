---
name: journal-setup
description: Use when the user runs `/journal-setup` (or asks to "bootstrap / set up the claude-journal data repo for the first time"). Interactive front door for first-time data-repo creation — checks tools, configures git identity, signs into gh when a remote is wanted, then drives the bootstrap and points to next steps. Run this once, before adding any device.
---

You are doing the **one-time, first-machine setup** of a brand-new
`claude-journal` *data* repo. `tools/journal/bootstrap.py` is the dumb,
strict tool that actually creates it; your job is the interactive layer it
refuses to do for itself: make sure git can commit, make sure `gh` is signed
in (if a remote is wanted), and then hand the bootstrap off so its secret
output never lands in this transcript.

The data repo path honors `$CLAUDE_JOURNAL_PATH` (default `~/claude-journal`).
The repo of *tools* (this checkout) is referred to below as `$TOOLS` — it is
the directory containing `scripts/bootstrap-journal-repo.sh`.

## Why a wrapper exists

`bootstrap.py` validates all of its preconditions up front and bails *before*
writing anything if any are unmet — a missing git identity, an unauthenticated
`gh`, or a pre-existing key. That is deliberate (it can never leave a
half-initialized repo behind), but it means a stranger hits a wall instead of
a fix. This skill turns each wall into an interactive remedy, then runs it.

## Step 0 — Idempotency / am-I-already-set-up check

Before anything, look for an existing setup and stop if found:

1. If `${CLAUDE_JOURNAL_PATH:-$HOME/claude-journal}/.git` exists, the data
   repo is already bootstrapped. Tell the user, show its remote
   (`git -C <path> remote -v`), and stop — point them at
   `tools/journal/init_device.py` (to add *this* device) or
   `/journal-schedule` (to create the consolidator routine) instead.
2. If `~/.claude/journal/git-crypt.key` already exists but the data repo does
   not, this is probably an *additional* device, not a first bootstrap — the
   key was placed out-of-band. Do **not** run bootstrap (it would refuse
   anyway). Point the user at the additional-device flow in the README
   (`init_device.py`) and stop.

## Step 1 — Required tools

Check each is on `PATH`: `git`, `git-crypt`, and — only if the user wants a
GitHub remote created — `gh`. For any that are missing, give the
platform-appropriate install hint and stop until they are present:

- macOS: `brew install git git-crypt gh`
- Debian/Ubuntu: `sudo apt install git git-crypt gh`
- RHEL/Oracle/Fedora: `sudo dnf install git git-crypt gh`

## Step 2 — Git commit identity (interactive)

The init commit needs `user.name` and `user.email`, or git aborts with
"empty ident name" on fresh machines. Check both:

```bash
git config --global user.name; git config --global user.email
```

If **either** is empty, prompt the user for the missing value(s) and set them
(confirm the exact name/email with the user first — do not invent them):

```bash
git config --global user.name "<their name>"
git config --global user.email "<their email>"
```

Re-run the check and confirm both now resolve before moving on. This is pure
local config — there is nothing to "sign into" here.

## Step 3 — Choose local-only vs. GitHub remote

Ask the user which they want:

- **GitHub remote** — bootstrap creates a **private** repo and pushes
  (`--repo <owner>/claude-journal`). Confirm the exact `owner/name`.
- **Local-only** — initialize on this machine only (`--no-remote`); they add
  a private remote later.

There is no public option. If the user is unsure, recommend the GitHub remote
(it is what every other device clones from).

## Step 4 — GitHub sign-in (only if a remote was chosen)

If and only if Step 3 chose a remote, confirm `gh` is authenticated:

```bash
gh auth status
```

If it reports **not** logged in, the user must sign in. `gh auth login` is
interactive (browser/device-code flow) and should run in *their* terminal, not
through you — have them run it via the `!` prefix so its output stays in the
session:

```
! gh auth login
```

Wait for them to finish, then re-run `gh auth status` and confirm it is
authenticated before continuing.

## Step 5 — Run the bootstrap (the user runs it, NOT you)

`bootstrap.py` prints the **git-crypt key** to stdout and pauses for the user
to back it up. That key must never pass through your tool output, because the
Stop hook pushes transcripts to the data repo — a leaked key there defeats the
encryption. So you do **not** run the bootstrap. Instead, print the exact
command and tell the user to run it themselves (in their terminal or via the
`!` prefix):

- Remote: `$TOOLS/scripts/bootstrap-journal-repo.sh --repo <owner>/claude-journal`
- Local-only: `$TOOLS/scripts/bootstrap-journal-repo.sh --no-remote`

Tell them what to expect: it creates the skeleton, initializes git-crypt,
**prints the key and stops** — they must save the key in a password manager and
type `saved` to continue. Losing the key makes every transcript, memory, and
proposal permanently unreadable.

Substitute `$TOOLS` with the real absolute path to this checkout.

## Step 6 — Verify (without ever reading the key)

After the user says the bootstrap finished and the key is backed up, confirm
the result **without printing the key**:

```bash
test -f ~/.claude/journal/git-crypt.key && echo "key present"
git -C "${CLAUDE_JOURNAL_PATH:-$HOME/claude-journal}" log --oneline -1
```

Never `cat`, `base64`, or otherwise echo `~/.claude/journal/git-crypt.key`.
If the verification fails, the bootstrap was strict-aborted by a precondition
— read the error the user saw, fix the precondition (Steps 1–4), and have them
re-run.

## Step 7 — Offer hands-off updates (auto-update)

This applies to the **plugin** install — how the user got this skill. (If the
journal tooling is instead a manual symlink install — no entry whose
`source.repo` ends in `/claude-journal-tools` in
`~/.claude/plugins/known_marketplaces.json` — skip this and tell them updates
come from a `git pull` of their checkout, not plugin auto-update.)

Third-party marketplaces have auto-update **off by default**, so new releases
won't reach the user unless they update by hand. Offer to fix that:

1. Find the journal marketplace's registered name — the key in
   `~/.claude/plugins/known_marketplaces.json` whose `source.repo` ends in
   `/claude-journal-tools` (fall back to `claude-journal-tools`).
2. Check `~/.claude/settings.json` for
   `extraKnownMarketplaces.<name>.autoUpdate`. If it is already `true`, tell the
   user auto-update is on and move on.
3. Otherwise ask whether they want hands-off auto-updates. If yes, **merge**
   this into `~/.claude/settings.json` — preserve every existing key; only add
   or extend `extraKnownMarketplaces`:

   ```json
   "extraKnownMarketplaces": {
     "<name>": {
       "source": { "source": "github", "repo": "<owner>/claude-journal-tools" },
       "autoUpdate": true
     }
   }
   ```

   Use the exact registered `<name>` from step 1 so it merges with the existing
   registration instead of creating a duplicate; substitute the real `<owner>`.
4. If they decline the settings edit, give them the manual alternative: `/plugin`
   → **Marketplaces** → `<name>` → **Enable auto-update**.

Either way, remind them updates only arrive when a new **version** is published
(the maintainer bumps `version` in the plugin manifest per release).

## Step 8 — Point at next steps

Once verified, tell the user the two remaining steps (do not run them here):

1. **Add devices.** On *every* device (including this one), set
   `CLAUDE_JOURNAL_REPO_URL` and run
   `tools/journal/init_device.py <device-name>`. Additional devices need the
   git-crypt key placed first, out-of-band (see README).
2. **Create the consolidator routine, once per account**, with
   `/journal-schedule`. It asks **how many times a day** to run — default is
   once (nightly); pick more only if you want distilled output to reach your
   other devices faster during the day (runs must be ≥1h apart and stay under
   your per-account daily run cap of ≈15) — then it picks a DST-safe time.

Also point out the **consolidator prompt**: bootstrap seeded
`consolidator/ROUTINE.md` into the new data repo from this tools repo's
bundled template (`$TOOLS/tools/journal/templates/ROUTINE.md`). That data-repo
copy is the **source of truth** for what the routine does — distilling
digests, memories, skill proposals, and CLAUDE.md-edit proposals. Tell the
user they can **edit it** to tune the distillation rules (or swap in their own
prompt entirely); after any edit they re-paste the body into the cloud routine
via `/journal-schedule` (or `/schedule update journal-consolidator`), since the
cloud config holds a copy that must be kept in sync.

## Guardrails

- **Never** let the git-crypt key (or its base64) reach your tool output. Do
  not run the bootstrap yourself, and never echo the keyfile.
- You only *validate and remedy* preconditions — the bootstrap is the single
  source of repo creation. Do not reimplement `git init` / `git-crypt init`
  here.
- Confirm any value you write into git config or pass as `--repo` with the
  user. Never guess a name, email, or repo owner.
- This is a first-machine action. If Step 0 shows an existing repo or key,
  stop and redirect — do not "re-bootstrap."
