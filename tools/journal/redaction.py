"""Shared secret-redaction for material pushed to the journal repo.

Used by `transcript.py` (conversation prose) and `state.py` (CLAUDE.md
snapshots) so both scrub the exact same set of patterns.

**This is defense-in-depth, NOT a security boundary.** The real protection is
that `raw/` and `state/` are git-crypt-encrypted at rest, so a secret that
doesn't match any pattern below is still ciphertext in the repo. Pattern-based
redaction only catches *known* key shapes that appear in text; treat it as a
courtesy scrub of the obvious, not a guarantee.

Each rule is a `(compiled_pattern, replacement)` pair. Most replace the whole
match with `[REDACTED]`; a few keep a non-secret prefix (the `Bearer ` literal,
a DB scheme + host, an `aws_secret_access_key=` label) via a `\\1` backref so
the surrounding context survives. Every pattern is anchored on a literal prefix,
marker, or vendor host so ordinary prose, slugs, and code are not clobbered.
"""
from __future__ import annotations

import re

REDACTION_RULES = [
    # Anthropic / OpenAI / OAuth "sk-…". Requires a 20-char UNBROKEN alphanumeric
    # run (which every real key has) so kebab-case slugs like
    # "sk-button-primary-large" or "sk-learn-classification" are NOT clobbered.
    (re.compile(r"sk-[A-Za-z0-9_-]*?[A-Za-z0-9]{20}[A-Za-z0-9_-]*"), "[REDACTED]"),
    # Stripe secret / restricted keys use an underscore, so they evade the sk- rule.
    (re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}"), "[REDACTED]"),
    # GitHub token family: ghp_ (classic), gho_ (OAuth), ghu_/ghs_ (app
    # user/installation), ghr_ (refresh). Fine-grained github_pat_ handled below.
    (re.compile(r"gh[opusr]_[A-Za-z0-9]{20,}"), "[REDACTED]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED]"),
    # Google OAuth client secret — fixed, distinctive vendor prefix.
    (re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"), "[REDACTED]"),
    # AWS access key id (long-term AKIA / temporary ASIA).
    (re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"), "[REDACTED]"),
    # AWS secret access key — the sensitive 40-char half. Anchored on the
    # canonical label so a bare 40-char base64 string isn't over-matched; keeps
    # the label, scrubs the value.
    (re.compile(r"(aws_secret_access_key\s*[=:]\s*[\"']?)[A-Za-z0-9/+]{40}", re.IGNORECASE), r"\1[REDACTED]"),
    # Google / GCP API key.
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "[REDACTED]"),
    # Slack tokens (bot/user/app/refresh/config).
    (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "[REDACTED]"),
    # Slack incoming-webhook URL — the secret is in the path, not an xox token.
    (re.compile(r"https://hooks\.slack\.com/(?:services|workflows)/[A-Z0-9]+/[A-Z0-9]+/[A-Za-z0-9]+"), "[REDACTED]"),
    # Authorization: Bearer <token>. Keep the "Bearer " literal, scrub the token.
    (re.compile(r"(bearer\s+)[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE), r"\1[REDACTED]"),
    # Database connection URI with embedded user:password@. Keep scheme + host,
    # scrub the credentials. Scheme-restricted, allows an empty user and an '@'
    # inside the password, and the lookahead anchors on the last '@' before host.
    (re.compile(r"((?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://)[^/\s]*:[^/\s]*@(?=[^/\s@]*[/\s:]|[^/\s@]*$)"), r"\1[REDACTED]@"),
    # JWT: header.payload(.signature). Third segment optional so unsigned
    # (alg:none) / two-segment tokens are caught too.
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]*)?"), "[REDACTED]"),
    # PEM private-key block (RSA/EC/DSA/OPENSSH/PGP). The negated-marker lazy
    # class `(?:(?!-----BEGIN )[\s\S])*?` avoids O(n^2) backtracking on many
    # BEGIN headers with no END (was ~7.4s on 256 KB; now ~ms), and the `|$`
    # tail still scrubs a block pasted without its END line.
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----(?:(?!-----BEGIN )[\s\S])*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"), "[REDACTED]"),
    # git-crypt symmetric keyfile, base64-encoded. Every git-crypt key starts
    # with the bytes b"\x00GITCRYPT"; base64 of those is always the prefix
    # "AEdJVENSWVBU". Catching that scrubs the key even mid-paragraph.
    (re.compile(r"AEdJVENSWVBU[A-Za-z0-9+/=]{50,}"), "[REDACTED]"),
]


def redact(text: str) -> str:
    """Replace every known secret pattern in `text` with `[REDACTED]`.

    Defense-in-depth only (see module docstring); not exhaustive. The real
    boundary is git-crypt encryption at rest.
    """
    for pattern, replacement in REDACTION_RULES:
        text = pattern.sub(replacement, text)
    return text
