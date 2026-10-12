# SHREKSICH-AI — buyer handover (preliminary)

This branch is a buyer-transfer snapshot of `feature/shreksich-ai`. Its Dockerfile restores the bot from `app.zip.b64` and applies patches at build time; audit all bundled files, dependencies and licenses before release.

## Setup
1. Copy `.env.sale.example` to `.env.sale` and replace placeholders.
2. Run `docker compose -f compose.sale.yml up -d --build` on buyer-owned Linux host.
3. Inspect logs; test /start, AI response and shop integration.
4. Restore verified AI database backup to the volume; ensure exact DB path is consistent with the original deployment before restoring.

Never run two polling instances with the same Telegram bot token simultaneously. The old service should be stopped only at the controlled cutover. No live build or functional verification has been completed for this buyer package.
