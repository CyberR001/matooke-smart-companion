# MatookeSmart Companion

**Your matooke. Better decisions. Better markets.**

A working prototype of the venture described in the concept proposal: an
agricultural intelligence companion for Uganda's matooke farmers, an
early-order marketplace that turns a future harvest into cash without a loan,
and the digital side of the MatookeSmart Hub that buys suitable surplus and
sells it as processed product.

Built for **IST2106 Technopreneurship**, Makerere University, Bachelor of
Information Systems and Technology - October 2026.

> **Read this first.** Every price, yield, cost and demand figure in the seeded
> database is **synthetic sample data**. The models, the rules and the maths are
> real; the numbers are placeholders waiting for field collection, exactly as
> sections 5.2, 5.3 and 14 of the proposal require ("use actual quotations,
> interview findings and processing trials rather than inventing revenue or
> profit claims"). No customer interviews have been run, so nothing here claims
> market validation.

---

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` - screens and API, no accounts needed.

```bash
docker compose up --build          # same app, PostgreSQL as section 7 specifies
python scripts/demo.py --quantity 120 --urgent 400000   # every module, in the terminal
pytest -q                          # 129 tests
```

## What is new in v0.2

Cleaner phone-first interface (bottom tab bar, hero landing), a **How it fits together** screen
(`/system`: layers, module status, live logical data model), `app/routers/`, security headers,
request IDs, write rate limiting, friendly error pages, `render.yaml` for free hosting, and
[`docs/LOGICAL_MODEL.md`](docs/LOGICAL_MODEL.md). The **farm doctor** and **price forecast** are
unchanged and labelled *prototype* everywhere. 129 tests.

## What is actually implemented

| Proposal | Module | Code |
| --- | --- | --- |
| 5.1 | Farm doctor - guided symptom questionnaire, expert-reviewable knowledge base, confidence, referral rules | [`app/engine/diseases.py`](app/engine/diseases.py) + [`knowledge/matooke_diseases.json`](app/engine/knowledge/matooke_diseases.json) |
| 5.2 | Market intelligence - moving averages, shrunk seasonal indices, clamped trend, **backtested** confidence and range | [`app/engine/prices.py`](app/engine/prices.py) |
| 5.2 | "When to sell" - ranked, priced options (sell now / wait / split / pre-order / process) instead of just a chart | [`app/engine/sell_advice.py`](app/engine/sell_advice.py) |
| 5.3 | Surplus and value addition - processing yield, full cost stack, margin, break-even, explainable product ranking, trials overriding assumptions | [`app/engine/products.py`](app/engine/products.py) |
| 5.4 | Early orders - advance-purchase terms, deposit cap, settlement split, state machine, crop-failure path, event log | [`app/engine/earlyorders.py`](app/engine/earlyorders.py) |
| 5.5 | Buyer matching - greedy, explainable scoring on distance, quantity, timing, price, grade | [`app/engine/matching.py`](app/engine/matching.py) |
| 5.6 | Opportunities - verification, expiry and staleness rules so nothing stale is shown as current | [`app/engine/opportunities.py`](app/engine/opportunities.py) |
| 5.7 | Membership - four tiers with safety-critical information exempt from every paywall | [`app/engine/entitlements.py`](app/engine/entitlements.py) |
| 6 | One composed decision for one farm | `GET /api/v1/farms/{id}/advice`, `app/services.py` |
| 16 | The four required screens, plus three supporting ones | [`app/templates/`](app/templates/) |

Full traceability in **[docs/MODULE_MAP.md](docs/MODULE_MAP.md)**, including the
parts that are **not** built.

### Screens (section 16)

| Screen | Path | What it answers |
| --- | --- | --- |
| Farmer Home Dashboard | `/dashboard` | price indicator, harvest date, health alerts, early-order opportunities, notices - and the suggested route with its money |
| Farm Doctor | `/farm-doctor` | "what is wrong and what do I do this week", as a *possible* condition with confidence, referral when unsure |
| When to Sell / Surplus | `/when-to-sell` | "given the market, what should I do with my matooke?" - every option priced, with risks |
| Early Orders & Marketplace | `/early-orders`, `/marketplace` | future supply, buyer demand, agreed terms, deposit, status, disputes |
| Hub & products | `/hub` | yield, cost stack, margin, Hub buying requirements, trial records |
| Price log | `/prices` | the record the whole model depends on, with source and verification status |
| Membership | `/tiers` | what each tier unlocks and what is never gated |

## The interesting engineering bits

- **Confidence is earned, not asserted.** The price model runs a rolling-origin
  backtest and derives `high / medium / low` from its own measured error. On
  thin or noisy history it *refuses* to project, and `sell_advice` will not
  recommend waiting for a better price when confidence is low. See
  `test_confidence_is_derived_from_backtest_not_asserted`.
- **Seasonal indices are shrunk toward zero** when a month is short on data, and
  the trend slope is clamped, so two months of records cannot produce a
  confident 40 % promise.
- **Assumptions are labelled and replaceable.** Product margins say
  `assumed` until a `ProductTrial` exists; recording a trial through
  `POST /api/v1/trials` immediately switches that product to `measured`.
- **Uncertainty is drawn, not hidden.** The chart is server-rendered SVG (no
  JS, no CDN): history solid, projection dashed, and a shaded range that widens
  with the horizon - low confidence is printed inside the image.
- **A pre-order is not a loan.** No interest exists in the code, deposits are
  capped at 60 % and the cap is disclosed, the buyer's balance and the
  platform's fee are settled as separate numbers, and a declared crop failure
  produces rescheduling options rather than a repayment demand.
- **Follow-up questions are chosen by simulated information gain** - the engine
  asks the question that most separates the leading candidate conditions, and
  stops when nothing left would change the ranking.
- **Rankings explain themselves.** Every match score and product score is
  returned with its components, so a farmer or a marker can disagree with a
  specific weight.

## Honest limits

- No authentication, no per-user isolation, no rate limiting: **do not expose
  this with real data** (see [docs/DEPLOYING.md](docs/DEPLOYING.md)).
- No image recognition. `ml/train_matooke_vision.py` is a scaffold that refuses
  to train on thin data; it is not imported by the app, so no one can mistake a
  placeholder for a model.
- No SMS/WhatsApp integration, no payment movement, no escrow, no inventory or
  batch-traceability system for the Hub.
- Prices are per bunch at a named market and grade; transport, haggle loss and
  spoilage in transit are not modelled.
- Zero customer interviews so far. [docs/VALIDATION.md](docs/VALIDATION.md) is
  the instrument to fix that, with kill thresholds written down in advance.

## Marketing asset (section 16)

The proposal asks for one digital marketing asset carrying the message
"Your matooke. Better decisions. Better markets.":

| File | Use |
| --- | --- |
| [`docs/assets/marketing_poster.png`](docs/assets/marketing_poster.png) | social and field-day poster, portrait |
| [`docs/assets/banner.svg`](docs/assets/banner.svg) | repository social preview, wide, vector so it stays sharp and searchable |

The poster is AI-generated concept artwork, not photography of a real farmer
and not a promise about prices - use it for the coursework pitch, and replace
it with a field-tested photo (with the farmer's written consent) before any
public campaign.

## Documentation

| File | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | system shape, why engines are pure functions, data flow of one decision |
| [docs/MODULE_MAP.md](docs/MODULE_MAP.md) | proposal section -> code -> status, including what is not built |
| [docs/DATA.md](docs/DATA.md) | provenance rules, audit tables, minimum collection routine, personal data |
| [docs/RESPONSIBLE_AI.md](docs/RESPONSIBLE_AI.md) | every safety behaviour, the words the UI may not use, what remains before real farmers |
| [docs/VALIDATION.md](docs/VALIDATION.md) | interview protocol, hypotheses with kill thresholds, experiment order |
| [docs/API.md](docs/API.md) | endpoint reference and the errors to expect |
| [docs/DEPLOYING.md](docs/DEPLOYING.md) | SQLite / Docker / Postgres, configuration, pre-pilot checklist |

## Coursework alignment (section 17)

| Expectation | Where it shows |
| --- | --- |
| Entrepreneurial mindset and opportunity | a crop-specific venture addressing glut, information gaps and urgent cash in one system |
| Venture and revenue model | subscriptions, buyer services, disclosed commission per completed order, Hub product margin (`products.py`, `earlyorders.py`) |
| Lean Build-Measure-Learn | stored `forecast_run`, `match_run`, `disease_case.farmer_rating` make the metrics queryable; hypotheses and kill thresholds in `docs/VALIDATION.md` |
| Market research | interview instrument and sampling plan ready to run - **not yet run, and not claimed** |
| Technology and innovation | statistical forecasting with backtesting, rule-based diagnosis with referral, explainable ranking and matching |
| Legal and ethical framework | consent columns, source attribution, no lending or custody code, "possible diagnosis" wording, UNBS flags |
| Feasibility and finance | yield/margin/break-even maths fed by trial records; no invented P&L |
| Communication and presentation | four screens, one composed API payload, this README, `scripts/demo.py` |

## Layout

```
app/
  main.py            FastAPI app, lifespan (create tables, seed if empty)
  api.py             JSON API under /api/v1
  pages.py           server-rendered mobile-first screens
  services.py        DB <-> engine glue
  models.py          SQLAlchemy domain model
  schemas.py         request validation
  charts.py          dependency-free SVG price chart
  seed.py            synthetic demo dataset (all rows marked synthetic)
  engine/            pure decision logic - no ORM, no framework
    prices.py  sell_advice.py  products.py  diseases.py
    matching.py  earlyorders.py  opportunities.py  entitlements.py
    knowledge/ matooke_diseases.json  matooke_products.json
  templates/ static/  screens, CSS, progressive enhancement only
tests/               129 tests across engines, API and screens
ml/                  image-model scaffold + the dataset plan that gates it
docs/                architecture, module map, data, responsible AI, validation, API, deploy
scripts/demo.py      terminal walkthrough of every module
```

## Licence

MIT - code only. It does not licence agricultural, medical or financial advice
the software may generate, and it transfers no rights in the concept proposal it
implements. See [LICENSE](LICENSE).
