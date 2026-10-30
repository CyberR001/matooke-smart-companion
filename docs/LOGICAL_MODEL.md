# Logical data model

Generated from `app/models.py` by `scripts/gen_logical_model.py`. Do not edit by hand.

```mermaid
erDiagram
  person ||--o{ buyer_requirement : "buyer_id"
  person ||--o{ farm : "owner_id"
  market ||--o{ forecast_run : "market_id"
  market ||--o{ price_record : "market_id"
  person ||--o{ price_record : "collector_id"
  person ||--o{ subscription : "person_id"
  person ||--o{ disease_case : "farmer_id"
  farm ||--o{ disease_case : "farm_id"
  person ||--o{ harvest_listing : "seller_id"
  farm ||--o{ harvest_listing : "farm_id"
  harvest_listing ||--o{ early_order : "listing_id"
  buyer_requirement ||--o{ early_order : "requirement_id"
  harvest_listing ||--o{ match_run : "listing_id"
  buyer_requirement ||--o{ match_run : "requirement_id"
  early_order ||--o{ order_event : "order_id"
  person {
    INTEGER id PK
    VARCHAR full_name
    VARCHAR phone
    VARCHAR email
    VARCHAR role
    VARCHAR district
    VARCHAR language
    VARCHAR tier
    DATETIME created_at
    BOOLEAN consent_profile
    BOOLEAN consent_images
    BOOLEAN consent_contact
  }
  subscription {
    INTEGER id PK
    INTEGER person_id FK
    VARCHAR tier
    INTEGER amount_ugx
    BOOLEAN price_is_hypothesis
    VARCHAR status
    DATE started_on
    DATE expires_on
  }
  farm {
    INTEGER id PK
    INTEGER owner_id FK
    VARCHAR name
    VARCHAR district
    VARCHAR parish
    FLOAT latitude
    FLOAT longitude
    FLOAT area_acres
    DATE planting_date
    DATE expected_harvest_date
    INTEGER matooke_stands
    FLOAT hands_per_bunch
    VARCHAR variety
    TEXT notes
  }
  market {
    INTEGER id PK
    VARCHAR name
    VARCHAR district
    FLOAT latitude
    FLOAT longitude
    VARCHAR unit
    BOOLEAN is_active
  }
  price_record {
    INTEGER id PK
    INTEGER market_id FK
    DATE observed_on
    INTEGER price_ugx
    INTEGER quantity_observed
    VARCHAR grade
    VARCHAR source
    BOOLEAN verified
    BOOLEAN is_synthetic
    INTEGER collector_id FK
    TEXT notes
  }
  forecast_run {
    INTEGER id PK
    INTEGER market_id FK
    DATETIME created_at
    INTEGER horizon_days
    VARCHAR method
    FLOAT mape_pct
    VARCHAR confidence
    JSON payload
  }
  disease_case {
    INTEGER id PK
    INTEGER farmer_id FK
    INTEGER farm_id FK
    DATETIME created_at
    VARCHAR image_path
    JSON answers
    JSON candidates
    FLOAT top_confidence
    BOOLEAN referred
    INTEGER farmer_rating
    VARCHAR expert_outcome
  }
  product_trial {
    INTEGER id PK
    VARCHAR product_key
    DATE trial_date
    FLOAT fresh_input_kg
    FLOAT output_kg
    FLOAT processing_hours
    INTEGER labour_ugx
    INTEGER energy_ugx
    INTEGER packaging_ugx
    INTEGER transport_ugx
    FLOAT spoilage_pct
    INTEGER selling_price_ugx_per_kg
    INTEGER fresh_price_ugx_per_kg
    TEXT notes
  }
  hub_buying_notice {
    INTEGER id PK
    VARCHAR title
    VARCHAR accepts
    VARCHAR accepts_form
    TEXT quality_spec
    INTEGER quantity_kg
    VARCHAR price_basis
    INTEGER price_ugx_per_unit
    VARCHAR district
    VARCHAR pickup_point
    DATE opens_on
    DATE closes_on
    INTEGER purchase_limit_kg
    VARCHAR status
  }
  harvest_listing {
    INTEGER id PK
    INTEGER seller_id FK
    INTEGER farm_id FK
    VARCHAR district
    INTEGER quantity_bunches
    FLOAT hands_per_bunch
    DATE expected_harvest_date
    VARCHAR quantity_confidence
    VARCHAR grade
    INTEGER asking_price_ugx_per_bunch
    INTEGER committed_bunches
    VARCHAR status
    TEXT notes
    DATETIME created_at
  }
  buyer_requirement {
    INTEGER id PK
    INTEGER buyer_id FK
    VARCHAR organisation
    VARCHAR product
    VARCHAR district
    INTEGER quantity_bunches
    DATE needed_by
    BOOLEAN is_recurring_weekly
    VARCHAR min_grade
    INTEGER max_price_ugx_per_bunch
    FLOAT willing_deposit_pct
    BOOLEAN accepts_future_harvest
    VARCHAR status
    TEXT notes
    DATETIME created_at
  }
  match_run {
    INTEGER id PK
    DATETIME created_at
    INTEGER listing_id FK
    INTEGER requirement_id FK
    FLOAT score
    JSON breakdown
    VARCHAR outcome
  }
  early_order {
    INTEGER id PK
    VARCHAR reference
    INTEGER listing_id FK
    INTEGER requirement_id FK
    INTEGER quantity_bunches
    INTEGER agreed_price_ugx_per_bunch
    FLOAT deposit_pct
    INTEGER advance_paid_ugx
    INTEGER balance_due_ugx
    FLOAT commission_pct
    INTEGER service_fee_ugx
    DATE delivery_date
    VARCHAR grade
    VARCHAR status
    VARCHAR cancellation_rule
    BOOLEAN crop_failure_declared
    JSON terms_snapshot
    DATETIME created_at
    DATETIME updated_at
  }
  order_event {
    INTEGER id PK
    INTEGER order_id FK
    DATETIME at
    VARCHAR actor
    VARCHAR kind
    TEXT note
  }
  opportunity {
    INTEGER id PK
    VARCHAR title
    TEXT summary
    VARCHAR kind
    VARCHAR source_name
    VARCHAR source_url
    TEXT eligibility
    TEXT how_to_apply
    JSON districts
    DATE opens_on
    DATE deadline
    DATE verified_on
    VARCHAR verified_by
    BOOLEAN is_verified
    VARCHAR status
    BOOLEAN requires_unbs
  }
```

## People and access (5.7)

### `person`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| full_name | VARCHAR |  |
| phone | VARCHAR |  |
| email | VARCHAR |  |
| role | VARCHAR |  |
| district | VARCHAR |  |
| language | VARCHAR |  |
| tier | VARCHAR |  |
| created_at | DATETIME |  |
| consent_profile | BOOLEAN |  |
| consent_images | BOOLEAN |  |
| consent_contact | BOOLEAN |  |

### `subscription`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| person_id | INTEGER | FK -> person |
| tier | VARCHAR |  |
| amount_ugx | INTEGER |  |
| price_is_hypothesis | BOOLEAN |  |
| status | VARCHAR |  |
| started_on | DATE |  |
| expires_on | DATE |  |

### `farm`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| owner_id | INTEGER | FK -> person |
| name | VARCHAR |  |
| district | VARCHAR |  |
| parish | VARCHAR |  |
| latitude | FLOAT |  |
| longitude | FLOAT |  |
| area_acres | FLOAT |  |
| planting_date | DATE |  |
| expected_harvest_date | DATE |  |
| matooke_stands | INTEGER |  |
| hands_per_bunch | FLOAT |  |
| variety | VARCHAR |  |
| notes | TEXT |  |

## Market intelligence (5.2)

### `market`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| name | VARCHAR |  |
| district | VARCHAR |  |
| latitude | FLOAT |  |
| longitude | FLOAT |  |
| unit | VARCHAR |  |
| is_active | BOOLEAN |  |

### `price_record`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| market_id | INTEGER | FK -> market |
| observed_on | DATE |  |
| price_ugx | INTEGER |  |
| quantity_observed | INTEGER |  |
| grade | VARCHAR |  |
| source | VARCHAR |  |
| verified | BOOLEAN |  |
| is_synthetic | BOOLEAN |  |
| collector_id | INTEGER | FK -> person |
| notes | TEXT |  |

### `forecast_run`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| market_id | INTEGER | FK -> market |
| created_at | DATETIME |  |
| horizon_days | INTEGER |  |
| method | VARCHAR |  |
| mape_pct | FLOAT |  |
| confidence | VARCHAR |  |
| payload | JSON |  |

## Farm doctor (5.1)

### `disease_case`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| farmer_id | INTEGER | FK -> person |
| farm_id | INTEGER | FK -> farm |
| created_at | DATETIME |  |
| image_path | VARCHAR |  |
| answers | JSON |  |
| candidates | JSON |  |
| top_confidence | FLOAT |  |
| referred | BOOLEAN |  |
| farmer_rating | INTEGER |  |
| expert_outcome | VARCHAR |  |

## Hub and products (5.3)

### `product_trial`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| product_key | VARCHAR |  |
| trial_date | DATE |  |
| fresh_input_kg | FLOAT |  |
| output_kg | FLOAT |  |
| processing_hours | FLOAT |  |
| labour_ugx | INTEGER |  |
| energy_ugx | INTEGER |  |
| packaging_ugx | INTEGER |  |
| transport_ugx | INTEGER |  |
| spoilage_pct | FLOAT |  |
| selling_price_ugx_per_kg | INTEGER |  |
| fresh_price_ugx_per_kg | INTEGER |  |
| notes | TEXT |  |

### `hub_buying_notice`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| title | VARCHAR |  |
| accepts | VARCHAR |  |
| accepts_form | VARCHAR |  |
| quality_spec | TEXT |  |
| quantity_kg | INTEGER |  |
| price_basis | VARCHAR |  |
| price_ugx_per_unit | INTEGER |  |
| district | VARCHAR |  |
| pickup_point | VARCHAR |  |
| opens_on | DATE |  |
| closes_on | DATE |  |
| purchase_limit_kg | INTEGER |  |
| status | VARCHAR |  |

## Marketplace and early orders (5.4, 5.5)

### `harvest_listing`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| seller_id | INTEGER | FK -> person |
| farm_id | INTEGER | FK -> farm |
| district | VARCHAR |  |
| quantity_bunches | INTEGER |  |
| hands_per_bunch | FLOAT |  |
| expected_harvest_date | DATE |  |
| quantity_confidence | VARCHAR |  |
| grade | VARCHAR |  |
| asking_price_ugx_per_bunch | INTEGER |  |
| committed_bunches | INTEGER |  |
| status | VARCHAR |  |
| notes | TEXT |  |
| created_at | DATETIME |  |

### `buyer_requirement`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| buyer_id | INTEGER | FK -> person |
| organisation | VARCHAR |  |
| product | VARCHAR |  |
| district | VARCHAR |  |
| quantity_bunches | INTEGER |  |
| needed_by | DATE |  |
| is_recurring_weekly | BOOLEAN |  |
| min_grade | VARCHAR |  |
| max_price_ugx_per_bunch | INTEGER |  |
| willing_deposit_pct | FLOAT |  |
| accepts_future_harvest | BOOLEAN |  |
| status | VARCHAR |  |
| notes | TEXT |  |
| created_at | DATETIME |  |

### `match_run`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| created_at | DATETIME |  |
| listing_id | INTEGER | FK -> harvest_listing |
| requirement_id | INTEGER | FK -> buyer_requirement |
| score | FLOAT |  |
| breakdown | JSON |  |
| outcome | VARCHAR |  |

### `early_order`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| reference | VARCHAR |  |
| listing_id | INTEGER | FK -> harvest_listing |
| requirement_id | INTEGER | FK -> buyer_requirement |
| quantity_bunches | INTEGER |  |
| agreed_price_ugx_per_bunch | INTEGER |  |
| deposit_pct | FLOAT |  |
| advance_paid_ugx | INTEGER |  |
| balance_due_ugx | INTEGER |  |
| commission_pct | FLOAT |  |
| service_fee_ugx | INTEGER |  |
| delivery_date | DATE |  |
| grade | VARCHAR |  |
| status | VARCHAR |  |
| cancellation_rule | VARCHAR |  |
| crop_failure_declared | BOOLEAN |  |
| terms_snapshot | JSON |  |
| created_at | DATETIME |  |
| updated_at | DATETIME |  |

### `order_event`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| order_id | INTEGER | FK -> early_order |
| at | DATETIME |  |
| actor | VARCHAR |  |
| kind | VARCHAR |  |
| note | TEXT |  |

## Opportunities (5.6)

### `opportunity`

| Field | Type | Key |
| --- | --- | --- |
| id | INTEGER | PK |
| title | VARCHAR |  |
| summary | TEXT |  |
| kind | VARCHAR |  |
| source_name | VARCHAR |  |
| source_url | VARCHAR |  |
| eligibility | TEXT |  |
| how_to_apply | TEXT |  |
| districts | JSON |  |
| opens_on | DATE |  |
| deadline | DATE |  |
| verified_on | DATE |  |
| verified_by | VARCHAR |  |
| is_verified | BOOLEAN |  |
| status | VARCHAR |  |
| requires_unbs | BOOLEAN |  |
