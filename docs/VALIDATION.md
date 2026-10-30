# Validation plan: what has to be proven before any of this is believed

Section 9 of the concept proposal requires evidence from at least ten
customer interviews, and it explicitly rejects the original three-response
survey as sufficient. **No interviews have been conducted for this repository
and no claim of validation is made anywhere in the code or UI.** This file is
the instrument, ready to run in the field.

## Who to talk to

| Group | Count | What we must learn |
| --- | --- | --- |
| Matooke farmers | 7-10 | how they decide when to sell; what they do about disease now; what an urgent cash need looks like in numbers; whether they would pre-book; what they would actually pay |
| Traders / retailers | 2-3 | sourcing pain, quality disputes, price swings, whether they would place a future order, demand for processed product |
| Institutional buyers (school, restaurant, hospital) | 1-2 | recurring quantities, procurement cycle, payment terms, whether a deposit is possible under their rules |
| Processor / extension officer | optional | real yields, drying windows, quality gates, how a diagnosis is actually confirmed |

Ask for a name and a number, and read the consent script before recording
anything personal. Interview in the language the farmer prefers.

## Question set (farmers)

1. Walk me through the last bunch you sold. Who bought it, what price, how did
   you decide that day?
2. When did you last sell at a price you were unhappy with? What forced it?
3. How do you find out what prices are doing now? What would have to be true
   for you to wait two more weeks?
4. Tell me about the last serious problem in the garden. Who did you ask, what
   did it cost, what did you do?
5. Have you ever lost a whole mat to wilt or Sigatoka? What happened to the
   planting material after that?
6. Think of the last time you needed money urgently - school fees, treatment,
   inputs. What did you do, and what did it cost you?
7. If a buyer offered to pay part of the price now for a harvest you have not
   picked yet, at a price you agreed today: what would worry you?
8. What would make you refuse a deposit? What would make a buyer refuse to
   give one?
9. Who should hold the money between agreement and delivery, and why do you
   trust them?
10. What happens to the surplus when prices collapse? Who processes it now, at
    what terms?
11. Have you ever sold flour, dried chips or crisps? What stopped it becoming
    regular?
12. What would you pay each month for this? (Ask after they have used the
    prototype, not before. Offer 0, 5,000, 10,000, 25,000 UGX and listen.)
13. Would you rather pay monthly, or per completed deal? Why?

## Hypotheses and the test that kills them

| Hypothesis | Metric | Kill threshold |
| --- | --- | --- |
| Farmers will record expected harvest date and quantity if it is quick | % of onboarded farmers with a listing within 7 days, minutes to complete | < 30 % or > 6 minutes |
| The sell advice changes behaviour | farmers who acted on a recommendation (follow-up call 2 weeks later) | < 2 in 10 |
| Forecasts are accurate enough to trust | realised price vs stored `forecast_run` at the same date | MAPE > 20 % over a quarter |
| Farmers want an advance against future harvest | listings receiving a buyer enquiry; deals agreed | < 1 deal in 20 listings |
| Buyers will pay a deposit | % of agreed orders with a deposit paid | 0 in 10 |
| Deposit size that both sides accept | terms actually agreed | negotiation never lands within 15-40 % |
| Processed product sells at a profit | trial unit economics + first 50 kg sold | gross margin < 15 % after real costs |
| Drying is the constraint, not the market | spoilage/rework rate in trials | > 15 % of output lost |
| Farmers find the disease advice understandable | `disease_case.farmer_rating`, and whether the action taken matched the advice | mean rating < 3.5/5 or harmful action |
| Referrals are practical | % of referred cases where an officer actually visited | < 50 % |
| A paid tier is viable | conversion, and churn at month 2 | < 5 % conversion or > 40 % churn |
| Opportunities are trusted | whether farmers act on a published notice and are not misled | any complaint of a stale notice |

## Experiment order (Build-Measure-Learn, section 10)

1. **Price dashboard, 2 markets, 6 weeks.** Does anyone record and read it? Cheapest
   experiment in the repository - it is already built.
2. **Ten manual early orders.** Broker them by phone, record them in the app
   afterwards. Learn which term causes arguments.
3. **One Hub buying notice for one product**, with a real trial batch. Does
   supply appear, and what does the yield actually come out as?
4. **Farm-doctor with 20 farmers plus an officer.** Is the wording
   understandable, and are referrals honoured?

Only after 1-4 do features like alerts, ratings or recurring procurement
deserve building.

## What "validated" would let us say

After 10+ interviews and the four experiments we could state a real price,
a measured yield, an observed take-up rate and an achieved margin in the
README. Until then the prototype's job is to make the *questions* cheap to ask,
and it is labelled accordingly.
