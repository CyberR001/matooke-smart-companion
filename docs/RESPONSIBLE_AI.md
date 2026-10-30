# Responsible AI, safety and the limits of this prototype

Section 12 and 13 of the concept proposal demand specific behaviour, not
sentiment. Every item below is implemented somewhere a test can see it.

## 1. No result is presented as certain

| Situation | Behaviour | Where |
| --- | --- | --- |
| Disease ranking | Headline is always "Possible <condition>"; the word "diagnosis" only appears as "not a guaranteed expert diagnosis" | `diseases.safe_headline` |
| Confidence | Mathematically capped at 0.95, because symptom matching cannot be certain | `diseases.CONFIDENCE_CAP` |
| Two conditions look alike | Referral instead of an answer (BXW vs Moko in the same season will do this) | `diseases.assess`, gap < 0.08 |
| Below the floor | Referral; floor 0.45 and configurable | `config.disease_referral_confidence` |
| Notifiable disease | BXW, Moko and bunchy top are *always* escalated regardless of score, because the response is community-level | `diseases.assess` |
| Price projection | Every forecast carries "not a guaranteed future price" plus an indicative range | `prices.PriceForecast.caveats` |
| Weak evidence | Confidence "low" -> the app **refuses** to recommend waiting for a better price | `sell_advice.advise` |
| Assumed economics | Any margin from the catalog is tagged `assumed` and notes that a trial is required | `products.estimate_economics` |

## 2. Free information stays free

`entitlements.SAFETY_CRITICAL` (disease advice, prevention, outbreak alerts,
basic trend, public opportunities, marketplace browsing, price recording,
cancelling an order) cannot be gated by any tier, and
`tests/test_entitlements.py` fails if it ever is. A subscription model that
withholds a blight warning is not a business, it is a hazard.

## 3. Not a lender, not a bank

- No interest appears anywhere in the order maths; the advance is a slice of an
  agreed sale price (`earlyorders.OrderTerms`).
- Deposits are capped at 60 % and the cap is *reported* to the caller, because
  a bigger advance shifts all crop risk to the buyer and needs custody.
- The app never holds money: `terms_snapshot.payment_note` says MatookeSmart
  records the order and an authorised partner moves the funds. No wallet, no
  escrow table exists in the schema - you cannot accidentally build a bank by
  forgetting to remove one.
- If a farmer loses the crop, `declare_crop_failure` offers rescheduling,
  partial supply or agreed cancellation - explicitly not an immediate
  repayment demand.
- The loan comparison in `urgency_alternative` is labelled as a benchmark with
  an assumed rate and is worded so it cannot read as an offer. Revisit with
  legal advice before showing it to real users at all.

## 4. Errors we expect to make, and how they are handled

| Failure | Mitigation in code |
| --- | --- |
| Price forecast is wrong | backtested MAPE shown, range widened when confidence is low, no "wait" advice on weak evidence, forecasts stored for later grading |
| Wrong disease suggested | referral thresholds, close-call detection, mandatory escalation for quarantine cases, `expert_outcome` recorded so mistakes become training data |
| Farmer over-promises a harvest | `quantity_confidence="low"` produces a warning at order creation; commit less than you expect |
| Buyer cancels after a deposit | written cancellation rule stored on every order, event log for the dispute |
| Crop failure | dedicated path, reschedule or partial supply, officer verification encouraged |
| Fraudulent "grant" | unverified notices are labelled and never shown as current; anything asking for a processing fee is reported, not published |

## 5. Words the UI is not allowed to use

Tests assert their absence on every screen: "guaranteed price", "will rise to",
"definitely". The screens must instead name the record count, the verified
count, the MAPE and the fact that the data is synthetic.

## 6. Still to do before real farmers use this

1. Expert review of `matooke_diseases.json` by an NVRI/district officer, and
   per-item provenance inside the JSON.
2. Privacy notice text in the languages the users speak, plus a withdrawal
   route and a retention period.
3. Legal review of deposit handling with the chosen payment partner.
4. UNBS/PFDA requirements confirmed for whichever product the Hub pursues.
5. An explicit "report a wrong answer" flow on the farm-doctor result (the data
   column exists, the UI path does not).
6. Rate limiting, authentication and per-user isolation - the prototype has no
   login, so it must not be exposed to the public internet with real data.
