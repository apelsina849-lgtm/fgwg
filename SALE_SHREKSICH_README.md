# SHREKSICH — full project sale preparation

**Scope:** Shreksich shop and SHREKSICH-AI only. Digital Bot Studio is excluded.

## Source
- Main shop: `shreksich-deploy/` on branch `sale/shreksich-full-transfer-20261012`.
- AI: branch `feature/shreksich-ai` (must be included separately in final delivery).
- Do not transfer unrelated branches or unrelated repositories.

## Buyer deployment (shop only, preliminary, not production-validated)
1. Install Docker Engine and Docker Compose plugin on buyer-controlled Linux host.
2. Copy `shreksich-deploy/.env.sale.example` to `shreksich-deploy/.env.sale` and fill all placeholders.
3. From `shreksich-deploy/`, run `docker compose -f compose.sale.yml up -d --build`.
4. Check `http://127.0.0.1:8000/health` on host and logs.
5. Configure a real HTTPS reverse proxy and `WEBAPP_URL`; verify Telegram Mini App, admin access, payments, and callbacks.
6. Deploy SHREKSICH-AI separately after auditing its branch, environment variables, and polling/webhook mode.

**Do not launch a second bot instance with the same token while the original is running.**

## Data migration
Existing Railway volumes: `shreksich-data` mounted at `/data` and `shreksich-ai-data` mounted at `/data` on different services. Database files must be exported with SQLite online backup or with the apps stopped; also preserve payout evidence and other uploaded assets. Do not export only a live SQLite .db file without accounting for WAL/shm. Test restoring backups to buyer-owned volumes before switching production.

## Handover checklist
- [ ] Source ownership and third-party licenses audited; transfer agreement signed.
- [ ] Main and AI services independently built and tested.
- [ ] Clean installation with buyer's Telegram token and owner ID.
- [ ] Payment flows and admin authorization tested.
- [ ] Real customer data transfer legally reviewed; privacy notices and retention obligations addressed.
- [ ] Backups restored and counts/balances reconciled.
- [ ] Buyer has their own hosting, domain, Git repository, and credentials.
- [ ] Rotate tokens, API keys, webhook secrets, and payment credentials after handover.
- [ ] Buyer signs acceptance after functional checks; seller revokes access.

## Exclusions and status
Digital Bot Studio, DigitalStudio-Robot, and DigitalStudio-MiniApp are excluded. This branch is a preparation workspace, not a certified production release. No live deployment, volume export, or end-to-end payment verification has been performed.
