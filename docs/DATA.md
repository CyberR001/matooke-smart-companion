# Data contract and provenance

## The one rule that matters here

Section 14 of the concept proposal says the team should use actual quotations,
interview findings and processing trials "rather than inventing revenue or
profit claims". This repository therefore never presents a number as fact:

| Kind of number | How it is produced | How it is labelled |
| --- | --- | --- |
| Market prices in the demo | `app/seed.py` generator: base level, seasonal shape, ~2 %/yr drift, +/-8 % noise, occasional shock | `is_synthetic=True` on every row; the banner on every screen; "synthetic" badge in tables |
| Real prices in a pilot | Field agent or farmer entry through `/prices` or `POST /api/v1/prices` | `is_synthetic=False`, `verified=False` until a supervisor checks it |
| Disease guidance | `knowledge/matooke_diseases.json`, written against publicly documented Ugandan banana guidance | every condition carries `references`; the JSON header states it is prototype text needing expert review |
| Product yields and costs | catalog assumptions in `knowledge/matooke_products.json` | `source="assumed"` on every result, plus a note telling the user to run a trial |
| Product yields once measured | `ProductTrial` rows (input kg, output kg, hours, costs, spoilage) | `source="measured"`, with the trial date in the note |
| Demand signals | `demand_signal` 0-1 with a `demand_basis` sentence | shown verbatim in the reasons list, phrased as an assumption |
| Opportunities | seeded illustrative notices, one deliberately unverified | source name, check date, verifier, expiry - computed, never stored as a claim |
| Buyer ceilings / deposit norms | seeded requirements | labelled as terms to agree, not market rates |

Nothing in this project claims a validated price, margin, tariff or adoption rate.

## Tables that exist to be audited

- `forecast_run` - API forecast requests are stored with its horizon, method, MAPE
  and confidence, so in six months we can grade what we said on 30 Oct 2026.
- `match_run` - suggested pairs with score breakdown and `outcome`, so the
  take-up rate of matching is a query, not a memory.
- `order_event` - who did what to an early order and when; disputes start here.
- `product_trial` - raw input, output, hours, costs, spoilage, notes. The
  engine prefers these numbers over any catalog assumption.
- `disease_case` - answers, ranked candidates, confidence, `referred`,
  `farmer_rating`, `expert_outcome`. This could contribute to a future validated dataset, subject to consent and review, and the evidence for whether the advice was useful.

## Minimum viable collection routine for a pilot

1. **Prices**: two markets, one person, twice a week. One row per market per
   date: price per bunch, grade, quantity seen, name of the trader spoken to.
   That is ~16 rows a month per market. Two years of weekly records (112 rows)
   is what this prototype needed before it would call a forecast "high
   confidence" - the model will not project on less than ~40 records.
2. **Trials**: one batch per product per season: weigh fresh in, weigh output
   out, record hours, all costs, spoilage, and the price actually achieved.
   Nothing is quoted as a margin without this.
3. **Disease cases**: photo + answers + officer verdict. The verdict is what
   makes the dataset worth anything.
4. **Buyer demand**: what the buyer said, quantity, price ceiling, whether
   they would really pay a deposit, and why not if they would not.

## Personal data

Fields that identify a farmer: name, phone, district/parish, coordinates,
photos, holdings, transaction records. Under the Data Protection and Privacy
Act 2019 the model stores explicit consent flags (`consent_profile`,
`consent_images`, `consent_contact`) rather than assuming it. Before a real
pilot: a short consent script in Luganda and English, a registration form that
states what is collected and why, a way to withdraw, and a retention period.
Coordinates are collected at parish level unless a farmer asks for precision -
a garden location is commercially sensitive when a buyer can see who has a
large uncommitted lot.

## What must be obtained, not generated

Market prices from MADS/UBOS series or direct trader quotes; UNBS requirements
for a specific product; bank/mobile-money partner terms for deposits; variety
and disease guidance from NARO/NVRI; soil and yield figures from a soil test.
