# Running it

## Zero-setup demo (SQLite)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed                       # optional: fills the demo dataset
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then: `http://localhost:8000/` for the screens, `/api/docs` for the API.
If the database is empty, the app seeds it on first start
(`SEED_DEMO_DATA=true`).

## Docker, with PostgreSQL as section 7 specifies

```bash
docker compose up --build        # web on :8000, Postgres on :5432
docker compose exec web python -m app.seed
```

The container runs as a non-root user and reports health on
`/api/v1/health`.

## Checks

```bash
pytest -q                        # 129 tests, in-memory database
ruff check app tests scripts ml  # CI runs this
ruff format --check app tests scripts ml
python scripts/demo.py --quantity 120 --urgent 400000
```

## Configuration

Copy `.env.example` to `.env`. Everything has a working default. The knobs that
change behaviour rather than cosmetics:

| Variable | Default | Effect |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/matookesmart.db` | set to Postgres for a pilot |
| `SEED_DEMO_DATA` | `true` | seed only when the database is empty |
| `DISEASE_REFERRAL_CONFIDENCE` | `0.45` | below this, the app refers to a person instead of answering |
| `MIN_ATTRACTIVE_MARGIN_PCT` | `15` | threshold before a product is called worthwhile |
| `DEFAULT_COMMISSION_PCT` / `DEFAULT_DEPOSIT_PCT` | `3` / `25` | starting terms in the order form - hypotheses, not tariffs |

Raising `DISEASE_REFERRAL_CONFIDENCE` makes the app *quieter* and safer;
lowering it makes it answer more often and is the wrong way to tune a health
tool. The forecast thresholds are currently fixed in the price engine; the corresponding settings are not wired into it.

## Notes before putting this in front of anyone

The prototype has **no authentication, no rate limiting and no per-user data
isolation**; every screen can read every farm. That is acceptable on a laptop
for a coursework demonstration and unacceptable on the public internet with
real farmer data. Before a pilot: users and sessions, consent capture with
retention and withdrawal, TLS, backups, then a privacy notice reviewed by
someone qualified, and the payment-partner conversation that section 13 of the
proposal requires.

Schema management is `create_all` for the prototype. Introduce Alembic as soon
as real data exists - after that, migrations are not optional.

## Free cloud hosting (Render)

1. Push this folder to a GitHub repository.
2. On render.com choose **New -> Blueprint** and select the repository. `render.yaml` does the rest.
3. Open the `onrender.com` URL it gives you.

Free instances sleep when idle (first load takes about a minute) and the demo SQLite file
resets on redeploy; the app re-seeds itself, so the demo always works. For real data set
`DATABASE_URL` to a PostgreSQL instance and `SEED_DEMO_DATA=false`. Other settings:
`RATE_LIMIT_PER_MIN` (default 120 writes/minute/client), `CORS_ORIGINS` (default none).
