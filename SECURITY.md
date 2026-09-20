# Security Policy

## Reporting a vulnerability

Please do not open a public issue for sensitive security reports.
Email the maintainer via GitHub profile or open a private security advisory.

## Secrets handling

- Never commit `.env` or `data/state.db`. They are gitignored.
- `.env.example` contains placeholder values only.
- Rotate `TELEGRAM_BOT_TOKEN` and `DHAN_ACCESS_TOKEN` immediately if you suspect exposure (regenerate via @BotFather and web.dhan.co).
- The systemd `token-refresh` timer renews Dhan tokens daily; manual token paste is only needed if the server was down >24h.

## Telegram permissions

Give the bot only Post + Edit rights in the channel. Do not add it as owner.

## Supported versions

Only the `main` branch on the latest release is supported.
