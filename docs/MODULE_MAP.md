# Proposal section -> code

Markers asked for this table: what in the concept proposal is actually built,
where it lives, and - just as important - what is *not* built.

| Proposal | What it asked for | Where it is | Status |
| --- | --- | --- | --- |
| 5.1 Farm doctor | Image-related input, follow-up questions, possible diagnosis, confidence, prevention, referral when unsure | `app/engine/diseases.py`, `app/engine/knowledge/matooke_diseases.json`, `/farm-doctor`, `POST /api/v1/doctor/assess` | Built with the questionnaire path the proposal specifies for a prototype. Image recognition **not** built (see `ml/`); image recognition is unavailable, and the app says so. |
| 5.2 When to sell | Prices, seasonality, harvest date and quantity in; direction, range, glut alert, confidence and options out | `app/engine/prices.py`, `app/engine/sell_advice.py`, `/when-to-sell`, `/api/v1/farms/{id}/advice` | Built: moving averages, shrunk seasonal indices, clamped trend, rolling-origin backtest for confidence, `ProductTrial`-free so far. Chart is SVG, drawn server-side. |
| 5.3 Surplus and trending products | Compare expected revenue against raw material, processing, packaging, transport, QC and selling costs; show whether the Hub is buying; measure yield in trial batches | `app/engine/products.py`, `knowledge/matooke_products.json`, `ProductTrial`, `HubBuyingNotice`, `/hub` | Built. 5 products, explainable 5-component ranking, trials override assumptions. **Demand signals are assumptions** until interviews replace them. |
| 5.4 Early orders | Farmer lists future harvest; buyer reserves; agreed price, deposit, delivery, cancellation, dispute handling; platform earns a disclosed fee | `app/engine/earlyorders.py`, `EarlyOrder`/`OrderEvent`, `/early-orders`, `/orders/{ref}` | Built as a state machine with a terms snapshot, deposit cap, short-delivery settlement and crop-failure path. **No money moves in code**: payment is described as a partner flow, and there is no wallet table at all. |
| 5.5 Marketplace and matching | Post requirements, list produce, match on location/quantity/date/quality/price, order status, history, dispute channel | `app/engine/matching.py`, `HarvestListing`, `BuyerRequirement`, `MatchRun`, `/marketplace` | Built (greedy, as allowed by section 7). Dispute channel = the order event log plus `disputed` status; no chat/messaging built. |
| 5.6 Government opportunities | Verify manually at first, show source, date checked, eligibility, deadline, filters | `app/engine/opportunities.py`, `Opportunity`, `/opportunities` | Built with enforcement in code: expired removed, unverified labelled and never marked current, stale verification downgraded. No scraping, as the proposal defers it. |
| 5.7 Membership and tiers | Four tiers; essential disease warnings and public information never withheld | `app/engine/entitlements.py`, `/tiers`, `tests/test_entitlements.py` | Built as a rule module plus a test that fails if a safety-critical feature is ever gated. No payment or billing. |
| 6 Example farmer journey | Modules have to work together for one farmer | `GET /api/v1/farms/{id}/advice`, `/dashboard` | Built: one call composes market intel, demand, Hub notice and product ranking. |
| 7 Technology and system design | FastAPI, Postgres, Pandas/Scikit-learn style stats, rules before CV, greedy matching, notifications, maps | `app/`, `docker-compose.yml` | Mostly built. **Notifications (SMS/WhatsApp) and map display are not** - there is no provider integration, only the data hooks for it. Distance uses approximate district centroids. |
| 9 Market validation | At least 10 real interviews | `docs/VALIDATION.md` | **Not done** - this repository cannot do it. The protocol and the questionnaire are ready to run; the findings are not in here and no claim of validation is made. |
| 10 MVP and Build-Measure-Learn | Register, log prices, sell advice, early orders, product list, disease advisory, opportunities + metrics | all of the above, `scripts/demo.py` | Built, with the measurement points stored (`forecast_run`, `match_run`, `farmer_rating`, `expert_outcome`). Experiments are specified, not yet run. |
| 11 Hub operations | Select products, publish specs, buy, inspect, weigh, batch IDs, process, record yields, sell | `HubBuyingNotice`, `ProductTrial`, `/hub` | Digital support only: notices, batch trial records, yield maths. No inventory, batch traceability ledger or weighing-station integration - a real pilot needs those before the Hub processes at scale. |
| 12 Risks and mitigation | Data quality, wrong diagnosis, unfulfilled orders, working capital, weak demand, low digital literacy, compliance | visible in code: confidence floors, referral, deposit caps, purchase limits, synthetic labels | Addressed where software can address them; the rest is process (see `docs/RESPONSIBLE_AI.md`). |
| 13 Legal and ethics | URSB/URA, Data Protection Act 2019, consent, UNBS, payment licensing, verified sources, no certainty claims | consent columns, source attribution, disclaimers, `requires_unbs` flag, no lending code | Partially: the software-side controls exist. Registration, certificates and legal review are human tasks not yet done. |
| 14 Financial framework | Revenue by stream, gross margin, processing yield, contribution per transaction, break-even, cash-flow timing | `app/engine/products.py` (yield, margin, break-even), `service_fee_ugx` (contribution) | Yield, margin and break-even maths are implemented and trial-fed. **No P&L, cash-flow forecast or unit-cost model is claimed** - the proposal forbids inventing those figures. |
| 15 Roadmap | Stages 1-6 | repository state | This is Stage 2 -> 3: a tested prototype ready for a small pilot. |
| 16 UI screens | At least three clear screens; four recommended | `app/templates/` | All four built, plus three supporting screens. |

## Coverage self-check

```bash
pytest -q            # 129 tests
ruff check app tests scripts ml
python scripts/demo.py --quantity 120 --urgent 400000
```

If you want a one-line answer to "is this the whole venture?" - no. It is the
decision-support and marketplace core, honestly labelled, with the physical
Hub represented by the two data objects it needs to coordinate (what it is
buying, and what the trials measured).
