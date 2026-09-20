# Contributing

Thanks for considering a contribution.

## Getting started

1. Fork the repo and clone your fork.
2. `cp .env.example .env` and keep `DRY_RUN=true`.
3. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
4. `pip install -r requirements.txt`
5. `python -m pytest -q` should show 42 passed.

## Guidelines

- Keep `DRY_RUN=true` for local dev so you don't spam a real channel.
- Add tests for new behavior (see `test_grouper.py` / `test_main.py`).
- Templates: validate placeholders via `template_engine.validate()` — unknown placeholders should be rejected.
- No secrets in commits. `.env`, `data/state.db`, `*.db` are ignored. If you accidentally stage them, `git reset`.

## Pull requests

- Small, focused PRs are easier to review.
- Include description, steps to reproduce, and test results.
- Update `CHANGELOG.md` under `Unreleased`.

## Code style

- Python 3.11+ (tested 3.13). Keep imports sorted, avoid adding heavy dependencies.
- Prefer explicit error handling for Telegram `BadRequest` / `RetryAfter`.

## Reporting issues

Use GitHub Issues. Include logs (`journalctl -u dhan-telegram -n 50`), sanitized `.env` keys (without values), and steps to reproduce — never paste tokens.
