# SSC-ICT Self Service Portal

Docker Compose-ready Self Service Portal/Webshop application based on the SSC-ICT factsheet assignment.

## What is included

- **Frontend:** React + TypeScript + Vite, served by Nginx.
- **API:** FastAPI.
- **Database:** SQLite persisted in a Docker volume.
- **Catalog:** Seeded from the supplied SSC-ICT factsheets.
- **Flows:**
  - Users can request and return services.
  - Expensive services require manager approval.
  - Users only see their own orders.
  - Managers see team orders but privacy-sensitive notes are hidden.
  - Admin can inspect all orders.
  - First Time Right validations before an order is accepted.
- **Accessibility:**
  - Semantic HTML.
  - Keyboard focus states.
  - Skip link.
  - Labels for form controls.
  - Responsive layout for desktop and phone.

## Demo users

The frontend contains a demo user switcher.

| User | Role |
| --- | --- |
| `lotte.devries@example.gov` | user |
| `mira.vandenberg@example.gov` | user |
| `h.vandermeer@example.gov` | manager |
| `daan.koster@example.gov` | admin |
| `no.basis@example.gov` | user without DWO Basis, API-only demo |

For API calls, authentication is simulated with the `X-User-Email` header. This is intentional for an assignment/demo project; replace it with real SSO/OIDC before production use.

## Run with Docker Compose

```bash
docker compose up --build
```

Open:

- Frontend: <http://localhost:8080>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

## Run backend tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

## Useful API examples

```bash
curl http://localhost:8000/api/services \
  -H "X-User-Email: lotte.devries@example.gov"

curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -H "X-User-Email: lotte.devries@example.gov" \
  -d '{"service_id": 7, "custom_name": "Programma-Duurzaamheid", "justification": "Projectteam"}'
```

## Production hardening backlog

- Replace demo header authentication with OIDC/SSO.
- Move from SQLite to PostgreSQL if concurrent production use is required.
- Add audit logging and immutable approval history.
- Add end-to-end browser tests.
- Add automated WCAG scans with axe-core.
- Add CI/CD workflow for tests, image build, and deployment.
