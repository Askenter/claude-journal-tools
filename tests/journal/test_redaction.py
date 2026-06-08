"""Tests for the shared secret-redaction patterns.

These exercise tools.journal.redaction.redact directly. The same function is
used by transcript.py (conversation prose) and state.py (CLAUDE.md snapshots),
so covering it here covers both call sites.

Positive cases assert the secret value is gone AND a [REDACTED] marker is
present. Negative cases assert benign text is left untouched (guarding against
over-redaction / false positives). Patterns and edge cases were chosen from an
adversarial stress test that executed redact() against crafted inputs.
"""
import time

from tools.journal.redaction import redact


# --- positive cases: these MUST be scrubbed ---------------------------------

def test_redacts_anthropic_openai_oauth_sk():
    for secret in (
        "sk-ant-api03-" + "A1b2C3d4E5f6G7h8I9j0Kk",   # has a 20+ unbroken run
        "sk-proj-" + "abcdefghij0123456789XY",
        "sk-" + "AbCdEf0123456789AbCdEf",
    ):
        out = redact(f"my key {secret} please")
        assert secret not in out and "[REDACTED]" in out


def test_redacts_stripe_keys():
    # NOTE: these fixtures are FAKE but secret-SHAPED so they exercise redact().
    # The tell-tale prefixes are split across `+` so the literal does not trip
    # GitHub push protection / secret scanners; at runtime each is the full
    # shape redact() must catch. (Do not "simplify" by joining the strings.)
    for secret in (
        "sk_li" + "ve_51H8xX2eZvKYlo2CabcdEfghIJklMNop",
        "sk_te" + "st_" + "0" * 24,
        "rk_li" + "ve_" + "abcdEFGH1234567890ijkl",
    ):
        out = redact(f"STRIPE={secret}")
        assert secret not in out and "[REDACTED]" in out


def test_redacts_github_token_family():
    for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"):
        secret = prefix + "A1b2C3d4E5f6G7h8I9j0"
        out = redact(f"token={secret}")
        assert secret not in out and "[REDACTED]" in out


def test_redacts_github_finegrained_pat():
    secret = "github_pat_" + "1" * 22 + "_" + "a" * 30
    out = redact(secret)
    assert "github_pat_" not in out and "[REDACTED]" in out


def test_redacts_google_oauth_client_secret():
    secret = "GOCSPX-1234567890abcdefghijklmn"
    out = redact(f'"client_secret": "{secret}"')
    assert secret not in out and "[REDACTED]" in out


def test_redacts_aws_access_key_id():
    for secret in ("AKIA" + "1234567890ABCDEF", "ASIA" + "1234567890ABCDEF"):
        out = redact(f"aws_access_key_id = {secret}")
        assert secret not in out and "[REDACTED]" in out


def test_redacts_aws_secret_access_key_value_keeps_label():
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"   # 40 chars, canonical example
    out = redact(f"AWS_SECRET_ACCESS_KEY={secret}")
    assert secret not in out
    assert "AWS_SECRET_ACCESS_KEY=" in out and "[REDACTED]" in out
    # also with spaces + quotes
    out2 = redact(f'aws_secret_access_key = "{secret}"')
    assert secret not in out2 and "[REDACTED]" in out2


def test_redacts_gcp_api_key():
    secret = "AIza" + "a" * 35
    out = redact(f"GOOGLE_API_KEY={secret}")
    assert secret not in out and "[REDACTED]" in out


def test_redacts_slack_token():
    # prefix split so the literal token shape doesn't trip secret scanners
    for secret in ("xox" + "b-2469135780-abcdefghijklmno", "xox" + "p-1111111111-2222222222-deadbeefcafe"):
        out = redact(f"SLACK_TOKEN={secret}")
        assert secret not in out and "[REDACTED]" in out


def test_redacts_slack_webhook_url():
    # host split so the literal webhook shape doesn't trip secret scanners
    secret = "https://hooks." + "slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
    out = redact(f"webhook: {secret}")
    assert secret not in out and "[REDACTED]" in out


def test_redacts_bearer_token_keeps_literal():
    token = "0123456789abcdef0123456789abcdef01234567"
    out = redact(f"Authorization: Bearer {token}")
    assert token not in out
    assert "Bearer [REDACTED]" in out


def test_redacts_db_uri_credentials_keeps_host():
    out = redact("postgres://admin:s3cr3tPass@db.example.com:5432/mydb")
    assert "s3cr3tPass" not in out
    assert "postgres://[REDACTED]@db.example.com:5432/mydb" == out


def test_redacts_db_uri_password_containing_at():
    out = redact("postgres://admin:s3cr3tP@ss@db.example.com:5432/mydb")
    assert "s3cr3tP@ss" not in out
    assert out == "postgres://[REDACTED]@db.example.com:5432/mydb"


def test_redacts_db_uri_empty_user():
    out = redact("redis://:s3cr3tpass@cache.example.com:6379/0")
    assert "s3cr3tpass" not in out and "[REDACTED]@" in out


def test_redacts_signed_jwt():
    secret = "eyJ" + "a" * 24 + "." + "b" * 24 + "." + "c" * 24
    out = redact(f"Authorization: Bearer {secret}")
    assert secret not in out and "[REDACTED]" in out


def test_redacts_unsigned_two_segment_jwt():
    secret = "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ"
    out = redact(f"token = {secret}")
    assert secret not in out and "[REDACTED]" in out


def test_redacts_pem_private_key_block_whole():
    block = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB\n"
        "AAAAMwAAAAtzc2gtZWQyNTUxOQAAACDdeadbeefdeadbeefdeadbe\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    out = redact(f"here is my key:\n{block}\nthanks")
    assert "PRIVATE KEY" not in out
    assert "b3BlbnNzaC1rZXktdjEA" not in out
    assert "[REDACTED]" in out


def test_redacts_pem_block_missing_end_marker():
    # A key pasted without its END line still gets scrubbed (|$ tail).
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAtruncatedbodydeadbeefdeadbeefdeadbeef\n"
    )
    out = redact(block)
    assert "MIIEpAIBAAKCAQEA" not in out and "[REDACTED]" in out


def test_redacts_git_crypt_keyfile_base64():
    secret = "AEdJVENSWVBUS0VZAAAAAgAAAAAAAAABAAAABAAAAAAAAAADAAAAIHQa168sk20F"
    out = redact(f"key blob {secret} end")
    assert "AEdJVENSWVBU" not in out and "[REDACTED]" in out


# --- negative cases: these MUST be left untouched (no false positives) ------

def test_does_not_redact_sk_kebab_slugs():
    for benign in (
        "sk-button-primary-large-rounded-xl",
        "sk-learn-classification-pipeline",
        "--sk-color-background-primary-hover",   # CSS custom property
        "sk-payment-gateway-service-prod",        # k8s label value
    ):
        assert redact(benign) == benign


def test_does_not_redact_credential_free_db_uris():
    for benign in (
        "redis://localhost:6379/0",
        "postgres://db.example.com/mydb",
        "see the postgresql://docs for details",
    ):
        assert redact(benign) == benign


def test_does_not_redact_bearer_prose():
    text = "the bearer of these tidings was unknown"
    assert redact(text) == text


def test_does_not_redact_gh_lookalike_words():
    for benign in ("github_actions_workflow_dispatch", "ghost_writer_application_name"):
        assert redact(benign) == benign


def test_does_not_redact_xoxo_prose():
    text = "love you, xoxo — see you tomorrow"
    assert redact(text) == text


def test_does_not_redact_bare_akia_word():
    text = "the AKIA prefix marks an AWS access key id"
    assert redact(text) == text


def test_does_not_redact_public_certificate():
    text = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBkTCB+wIJAKHHIG... (public)\n"
        "-----END CERTIFICATE-----"
    )
    assert redact(text) == text


def test_does_not_redact_eyj_non_jwt():
    text = "eyJob_count was 5 today"   # eyJ… but not a dotted multi-segment token
    assert redact(text) == text


def test_does_not_redact_short_sk_dash():
    text = "the sk-x flag is short"
    assert redact(text) == text


def test_leaves_ordinary_prose_untouched():
    text = "We deploy via docker compose and prefer terse responses."
    assert redact(text) == text


# --- robustness: the PEM rule must not blow up (ReDoS regression) -----------

def test_pem_redaction_is_not_quadratic():
    # ~256 KB of BEGIN-only headers with no END marker. The old `.*?` under
    # DOTALL took ~7.4s here; the negated-marker rewrite is ~ms.
    pathological = "-----BEGIN RSA PRIVATE KEY-----\n" * 8000
    start = time.monotonic()
    redact(pathological)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"redact() took {elapsed:.2f}s on repeated BEGIN headers (ReDoS)"
