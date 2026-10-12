# Full SHREKSICH transfer checklist

## Included
- Shop source: branch `sale/shreksich-full-transfer-20261012`, folder `shreksich-deploy/`.
- AI source: branch `sale/shreksich-ai-transfer-20261012`.
- Deployment configuration and documented settings.
- Domain, Telegram bot ownership/control and customer data **only when explicitly included in contract and legally transferable**.

## Explicitly excluded
Digital Bot Studio, DigitalStudio-Robot, DigitalStudio-MiniApp, their code, domains, credentials and databases; unrelated GitHub branches.

## Before signing
- [ ] Confirm actual legal owner(s) of all source code, images, text, libraries and branding.
- [ ] Prepare inventory of components, known bugs, dependencies and third-party services.
- [ ] Check whether PUBG branding/assets require permission; do not claim PUBG/KRAFTON affiliation.
- [ ] Audit payments, user balances, refund obligations and outstanding seller payouts.
- [ ] Identify privacy obligations for any personal data migration.
- [ ] Agree exact sale assets, warranties, support duration, price, payment and dispute jurisdiction.

## After contract / protected payment
- [ ] Buyer provisions their own Git hosting, HTTPS domain, VPS, Telegram bot ownership and payment settings.
- [ ] Export **consistent** shop and AI database backups plus evidence uploads from old Railway volumes.
- [ ] Record counts of users, orders, balances, payouts and inventory for reconciliation without publicly exposing personal data.
- [ ] Deploy two isolated services on buyer's infrastructure with buyer-controlled credentials.
- [ ] Restore backups and validate checksums and reconciliation counts.
- [ ] Test login, shop, Telegram Stars, admin roles, farm, cases, roulette, quiz, seller payouts and AI.
- [ ] Stop old instances before enabling buyer's polling/webhooks; prevent double processing.
- [ ] Transfer agreed domains and bot ownership only after payment protection and verified acceptance criteria.
- [ ] Rotate all credentials and revoke seller access after signed acceptance.
- [ ] Keep agreed records for accounting/legal obligations; delete only data eligible for deletion.

## Current blockers
- Railway trial expired; database export is not available yet.
- No end-to-end test or buyer-owned server provisioned.
- Source bundles have not been security/license audited; sale branches are **not** final deliverables.
