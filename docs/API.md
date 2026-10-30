# API reference

OpenAPI UI at `/api/docs`, schema at `/api/openapi.json`. Everything below is
what the screens use, so it is a real contract, not a parallel implementation.

| Method | Path | Purpose | Notable behaviour |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | liveness | returns the synthetic-data disclaimer |
| GET | `/api/v1/markets` | market list | latest price plus `synthetic` flag |
| GET | `/api/v1/markets/{id}/prices?days=` | history | each row carries `source`, `verified`, `synthetic` |
| POST | `/api/v1/prices` | record an observation | future dates rejected (422); new rows land unverified |
| GET | `/api/v1/markets/{id}/forecast?horizon_days=` | price outlook | confidence from backtest; empty `points` when history is too thin; stores a `forecast_run` |
| GET | `/api/v1/farms/{id}/advice?urgent_need_ugx=&quantity_bunches=&harvest_date=` | composed decision | market + demand + Hub + product ranking in one payload |
| GET | `/api/v1/doctor/questions` | questionnaire | states that image recognition is not enabled |
| POST | `/api/v1/doctor/assess` | rank conditions | saves a `disease_case`; `referred` true when unsure or notifiable |
| POST | `/api/v1/doctor/feedback?case_id=&rating=` | usefulness 1-5 | the section 10 metric |
| GET | `/api/v1/products/recommend?fresh_kg=&services_list=` | ranked products | `source` = measured/assumed per product |
| GET | `/api/v1/products/{key}/economics?fresh_kg=\|target_output_kg=` | full cost stack | back-solves fresh weight from a required output |
| GET | `/api/v1/products/{key}/income-target?target_income_ugx=` | kg needed to earn X | refuses when per-kg margin is not positive |
| POST | `/api/v1/trials` | record a trial batch | output > input rejected; overrides the assumption afterwards |
| GET/POST | `/api/v1/listings` | farmer supply | past harvest date rejected; quantity must be > 0 |
| GET/POST | `/api/v1/requirements` | buyer demand | deposit willingness and recurrence recorded |
| GET | `/api/v1/matches?min_score=` | suggested pairs | score with per-component breakdown and reasons |
| POST | `/api/v1/matches/run` | persist suggestions | writes `match_run` so take-up is measurable |
| POST | `/api/v1/orders` | draft an early order | over-commitment refused; deposit capped at 60 % and reported; spot delivery refused |
| GET | `/api/v1/orders`, `/api/v1/orders/{ref}` | list / detail | includes events and allowed next statuses |
| POST | `/api/v1/orders/{ref}/transition` | advance the lifecycle | illegal moves return 409 with the allowed set |
| POST | `/api/v1/orders/{ref}/settle` | close with real quantity | splits buyer balance, farmer share and platform fee; shortfalls priced at agreed rate |
| POST | `/api/v1/orders/{ref}/crop-failure` | declare failure | returns reschedule/partial options, not a demand note |
| GET | `/api/v1/opportunities?district=&kind=` | verified notices | unverified/expired/stale never shown as current |
| GET | `/api/v1/hub/notices` | what the Hub buys | includes per-farmer purchase limit |
| GET | `/api/v1/tiers` | membership model | lists what is never gated; prices marked as hypotheses |
| GET | `/api/v1/dashboard?farm_id=&urgent_need_ugx=` | farmer home payload | screens and API read the same object |

## Errors you should expect

- `422` - validation: future price date, past harvest date, zero quantity,
  impossible trial yield, over-committed listing, delivery too soon for an
  early order.
- `409` - a state change the order lifecycle does not allow, e.g. settling an
  order that was never delivered.
- `404` - unknown market, farm, product key or order reference.

Errors are returned as human sentences, because a field agent reading them on
a phone is the actual user.
