# Nanobot Security Review

**Reviewed**: 2026-02-10
**Reviewer**: Ben Lamm + Claude
**Verdict**: Safe for personal use. No malicious code. Credential handling needs manual hardening.

## Summary

~3,500 lines of Python. Clean, readable, well-organized. No telemetry, no backdoors, no phone-home behavior.

## Architecture

```
~/.nanobot/
├── config.json          # ALL credentials (plaintext JSON)
├── workspace/           # Session data, memory
├── media/               # Downloaded files from channels
├── logs/                # Application logs (unbounded, no rotation)
├── whatsapp-auth/       # WhatsApp bridge auth data
└── history/cli_history  # CLI input history
```

## Credential Flow

1. Config loaded from `~/.nanobot/config.json` (Pydantic validation)
2. Environment variables (`NANOBOT_*`) can override any config value
3. API keys are set in `os.environ` at runtime (visible to child processes)
4. Keys passed directly to LiteLLM's `acompletion()` calls
5. Platform tokens passed to respective SDK constructors

## Security Findings

### Critical
- **Plaintext config**: All API keys, tokens, email passwords in `~/.nanobot/config.json`
- **No enforced file permissions**: Config created with default umask, not 0600
- **Env var exposure**: API keys in `os.environ` for entire process lifetime

### High
- **No log masking**: Credentials could appear in error logs
- **Email passwords**: IMAP/SMTP passwords stored plaintext
- **No log rotation**: Logs accumulate at `~/.nanobot/logs/` without bounds

### Medium
- **Shell execution**: Agent can run shell commands; deny-patterns are regex-based (bypassable)
- **SSRF potential**: Web tool doesn't block internal IP ranges
- **Media downloads**: No file size limits from messaging platforms
- **Session data**: Chat history stored unencrypted on disk

### Not Issues (Verified Clean)
- No hardcoded credentials in source code
- No telemetry, analytics, or tracking
- All external connections use HTTPS/WSS
- No unexpected network destinations
- Pydantic validates config schema
- Shell deny-patterns block obvious attacks (rm -rf, mkfs, dd, fork bombs)
- Explicit consent flag required for email access

## Required Hardening (Do After Setup)

```bash
# 1. Lock down config file
chmod 600 ~/.nanobot/config.json

# 2. Lock down the entire nanobot directory
chmod 700 ~/.nanobot

# 3. Use env vars for the most sensitive keys instead of config
export NANOBOT_PROVIDERS__ANTHROPIC__API_KEY="sk-..."
export NANOBOT_PROVIDERS__OPENAI__API_KEY="sk-..."
```

## Dependencies

| Package | Risk | Notes |
|---------|------|-------|
| litellm | Low | Popular multi-LLM abstraction, handles credentials |
| pydantic | None | Config validation |
| httpx | None | HTTP client with SOCKS support |
| websockets | Low | History of DoS vulns, pinned >=12.0 |
| python-telegram-bot | None | Official SDK |
| slack-sdk | None | Official SDK |
| loguru | None | Logging library |

## Threat Model

**Appropriate for:**
- Personal single-user systems (laptop/desktop)
- Development environments
- Trusted networks

**Not appropriate for:**
- Multi-user / shared hosting
- Production / high-sensitivity use
