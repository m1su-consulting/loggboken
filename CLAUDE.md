# Implementationsplan: Loggboken (Environment Inventory)

Produktnamnet är **Loggboken** — i samma tema som idp:n "Kompassen". Repo-katalogen
heter fortfarande `environment-inventory`.

## Mål
Bygga ett backend-system som tar emot och lagrar information om vilka artefakter (paket, container-images m.m.) som är installerade i olika typer av miljöer. Data skickas in via REST från externa källsystem (RPM-baserade system, Kubernetes) i två mönster: händelse-baserad (enskild installation) och snapshot-baserad (hela miljöns nuvarande state).

Frontend (`frontend/`, React + Vite + TypeScript) ligger i samma repo som backend — enkelt internt verktyg, samma team äger båda, ingen fördel av separata repos/CI-cykler i detta läge.

## Kontext
- Språk/verktyg: Python, pakethantering med `uv`
- Webbramverk: FastAPI (förslag — byt om annat föredras)
- Databas: PostgreSQL
- Datainmatning: externa system POST:ar JSON till våra endpoints (push-modell)
- Två källsystem till att börja med: RPM-baserade paket och Kubernetes
- Samma artefakt kan finnas i flera miljöer samtidigt (many-to-many)
- Historik krävs: när blev något installerat/borttaget
- Lokal utveckling: hela stacken (API + PostgreSQL) ska kunna startas med `docker-compose up`; testdata ska kunna laddas in enkelt (t.ex. seed-script) för manuell test av endpoints utan att behöva bygga upp state för hand
- **`docker compose up -d` (standard, ingen flagga) är produktionslikt och börjar alltid tomt** — seedas aldrig automatiskt. Vill man peta med exempeldata kör man en helt separat instans (`-p loggboken-test`, samma `docker-compose.yml`) och seedar bara den — Docker Composes projektnamn ger fullständig isolering (egen databas/volym/nätverk), ingen risk att konfigurationerna glider isär. Se README "Kom igång lokalt" / "Testa mot exempeldata"

## Datamodell

```sql
environments
  id              UUID PRIMARY KEY
  name            TEXT NOT NULL         -- logisk identifierare, t.ex. namespace eller RPM-källans egen ID
  source_type     TEXT NOT NULL         -- 'rpm' | 'kubernetes' | ...
  host_or_cluster TEXT                  -- hostname (RPM) eller klusternamn (k8s)
  metadata        JSONB
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

artifacts
  id              UUID PRIMARY KEY
  name            TEXT NOT NULL
  version         TEXT NOT NULL
  source_type     TEXT NOT NULL
  raw_data        JSONB                 -- originaldata för spårbarhet
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  UNIQUE (name, version, source_type)

installations
  id                 UUID PRIMARY KEY
  environment_id     UUID NOT NULL REFERENCES environments(id)
  artifact_id        UUID NOT NULL REFERENCES artifacts(id)
  first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  last_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now()
  removed_at         TIMESTAMPTZ
  status             TEXT NOT NULL DEFAULT 'active'   -- 'active' | 'removed'
  source_of_removal  TEXT                              -- 'snapshot_diff' | 'manual' | NULL
  raw_data           JSONB
  UNIQUE (environment_id, artifact_id)

-- Index för snabba uppslag åt båda hållen
CREATE INDEX ON installations (environment_id);
CREATE INDEX ON installations (artifact_id);
```

**Designbeslut inbakade:**
- `environments.name` är den logiska identifieraren (t.ex. namespace); `host_or_cluster` är separat metadata om *var* miljön finns (host för RPM, kluster för k8s) — identitet och plats hålls isär
- `artifacts` är unika per (namn, version, källtyp) — samma artefakt kan referera till många `installations`
- `installations` är kopplingstabellen och bär all historik/status — en rad per (miljö, artefakt)-par, uppdateras snarare än att nya rader skapas vid removal
- `UNIQUE (environment_id, artifact_id)` gör atomär upsert möjlig och förhindrar dubbletter vid samtidiga requests

## Ingestion-mönster (två distinkta flöden)

**A) Händelse-baserad** — "artefakt X installerades i miljö Y nu"
- Atomär upsert via `INSERT ... ON CONFLICT (environment_id, artifact_id) DO UPDATE SET last_seen_at = now(), status = 'active'`
- Ingen diff-logik behövs

**B) Snapshot-baserad** — "så här ser hela miljön ut just nu" (t.ex. nattligt jobb)
- Jämför inkommande lista av artefakter mot nuvarande `active`-rader för miljön
- Finns i snapshot men saknas i databas → upsert som `active`
- Är `active` i databas men saknas i snapshot → markera `removed`, sätt `removed_at`, `source_of_removal = 'snapshot_diff'`
- Snapshot är sanningskälla vid konflikt mot en tidigare händelse-baserad post

**C) Manuell borttagning**
- Explicit endpoint för att markera en installation som borttagen, `source_of_removal = 'manual'`

## Steg

### 1. Projektuppsättning
- Initiera projekt med `uv init`
- Lägg till kärnberoenden: FastAPI, `asyncpg` (eller `psycopg`), `alembic` för migrationer
- Sätt upp projektstruktur: `/app`, `/migrations`, `/tests`
- `Dockerfile` (bygger appen) + `docker-compose.yml` (app + PostgreSQL) så hela stacken kan startas med `docker compose up -d --build`

*Klart när:* `uv run` startar en server som svarar på en health-check-endpoint, och `docker-compose up` ger en fungerande lokal PostgreSQL

### 2. Databasschema och migrationer
- Skapa Alembic-migration för `environments`, `artifacts`, `installations` enligt schema ovan
- Konfigurera `asyncpg`-pool med rimlig `min_size`/`max_size` för samtidig belastning
- Seed-script/fixture för testdata (exempel-environments, artifacts, installations) så manuell test av endpoints inte kräver att man bygger upp state för hand

*Klart när:* Migrationer körs rent mot en tom PostgreSQL-databas, alla tabeller, constraints och index skapas korrekt; seed-scriptet fyller databasen med användbar testdata med ett kommando

### 3. Källsystem-parsers
- Gemensamt interface: `BaseSourceParser.parse(raw_json) -> list[ArtifactInstallation]`
- `RpmSourceParser`: extraherar paketnamn, version, arch; miljö = värdspecifik identifierare (ej hostname i sig — se `environments.name` vs `host_or_cluster`)
- `KubernetesSourceParser`: extraherar container-image som artefakt; miljö = namespace, `host_or_cluster` = klusternamn
- Varje parser normaliserar till intern representation men behåller `raw_data` för spårbarhet
- Hantera trasig/ofullständig indata utan att krascha hela requesten

*Klart när:* Varje parser har enhetstester med exempel-payloads (giltiga och trasiga)

### 4. Ingestion-API
```
POST /api/v1/installations
  → händelse-baserad (mönster A): upsert, status=active, last_seen_at=now()

POST /api/v1/environments/{id}/snapshot
  → snapshot-baserad (mönster B): kör diff-logik, markerar saknade som removed

POST /api/v1/environments/by-name/{name}/snapshot?source_type=...
  → samma som ovan men adresserad via (name, source_type) istället för UUID —
    genväg för källsystem som bara känner sitt eget namn och inte vill cacha ett UUID

DELETE /api/v1/installations/{id}
  → manuell borttagning (mönster C): status=removed, removed_at=now(), source_of_removal=manual

GET /api/v1/environments
  → lista miljöer, med paginering och filter (source_type, host_or_cluster)

GET /api/v1/environments/{id}/installations
  → nuvarande state (status=active som default, ?include_removed=true för historik,
    ?artifact_name=... för att slå upp en specifik artefakt i miljön)

GET /api/v1/environments/by-name/{name}/installations?source_type=...&artifact_name=...
  → samma som ovan men adresserad via (name, source_type) istället för UUID —
    sök ut en specifik artefakt i en specifik miljö med bara namn, inget UUID behövs

GET /api/v1/artifacts/{id}/environments
  → var finns denna artefakt (omvänd fråga)

GET /api/v1/installations?q=...&environment=...&source_type=...&include_removed=...&sort_by=...&sort_dir=...
  → global sök över ALLA installationer (över alla miljöer), joinar in miljö- och
    artefaktinfo. q = fritext över miljönamn/host/artefaktnamn (ILIKE).
    environment = precist filter (till skillnad från q): exakt namn ELLER
    "prefix-"-gruppering, t.ex. environment=proj1 matchar både miljön "proj1"
    och alla "proj1-xxx" (Kubernetes-namespaces som delar projektprefix).
    sort_by: environment_name|host_or_cluster|artifact_name|artifact_version|status|
    first_seen_at|last_seen_at. Detta är datakällan för frontendens tabell.

GET /api/v1/environments/diff?left=...&right=...&source_type=...
  → ställer två miljöer (eller projektprefix-grupper, samma matchning som
    environment-filtret ovan) sida vid sida. Aggregerar aktiva installationer
    per sida (om prefixet matchar flera namespaces behålls varje namespace för
    sig) och returnerar per artefakt: left/right (lista av
    {environment_name, version} — visar exakt vilket specifikt namespace
    artefakten kommer från, inte bara den aggregerade prefix-frågan) och
    status (same|different|left_only|right_only). Ren beräkningslogik i
    app/diffing.py, enhetstestad utan databas.
```

*Klart när:* Alla endpoints testade manuellt (curl/httpie), korrekta statuskoder (200/201/400/404/409/422)

### 5. Samtidighetshantering
- Atomär upsert via `INSERT ... ON CONFLICT` för mönster A (inte "kolla om finns → skapa/uppdatera" i applikationskod)
- Snapshot-endpointen (mönster B) skyddas mot dubbel körning för **samma miljö**: enkel konflikt-avvisning (t.ex. `environments.snapshot_in_progress`-flagga eller kort-livad status-rad) som ger `409 Conflict` om en snapshot för samma `environment_id` redan pågår
- Samtidiga anrop för **olika** miljöer kräver ingen särskild hantering — PostgreSQL hanterar radlåsning naturligt per rad/transaktion

*Klart när:* Lasttest med parallella requests mot samma miljö ger inga dubbletter eller race conditions; parallella requests mot olika miljöer hanteras utan fördröjning av varandra

### 6. Felhantering och validering
- Tydliga felresponser, t.ex. `{"error": "unsupported_source", "detail": "..."}`
- Validera payload-struktur innan parsing (storlek, grundfält)
- Vid parse-fel: spara raw payload med status "failed" istället för att tappa data tyst

*Klart när:* Trasiga payloads ger begripliga felmeddelanden, inget kraschar, ingen data tappas tyst

### 7. Autentisering (grundnivå)
- API-nyckel per klientsystem (`X-API-Key`-header) — men **bara på skrivande endpoints**
  (`POST /installations`, `POST .../snapshot`, `DELETE /installations/{id}`).
  Läs-endpoints (`GET`, `/health`) kräver ingen nyckel — internt system, teamen ska
  kunna scripta mot läsning utan att först provisionera en nyckel.
- Nycklar kopplade till vilka `source_type` de får skriva till, om relevant

*Klart när:* Skrivande requests utan giltig nyckel avvisas med 401

### 8. Tester
- Integrationstester för båda ingestion-mönstren (händelse och snapshot), inkl. diff-logiken i mönster B
- Konkurrenstest: parallella requests mot samma (environment, artifact) ska inte skapa dubbletter
- Tester för query-endpoints (lista, filter, paginering, include_removed)
- Uppdelning `tests/unit/` (ingen databas, mockad `asyncpg.Connection` där så behövs: parsers, auth-logik, middleware, ingestion-orkestrering) vs. `tests/integration/` (riktig Postgres, hela HTTP-stacken) — se README för hur man kör vardera lokalt
- GitLab-pipeline (`.gitlab-ci.yml`): `unit-tests` körs på varje push/MR utan databas; `integration-tests` körs bara på MR mot `main` (startar en disponibel Postgres-service)

### 9. Frontend (samma repo)
- `frontend/`: React + Vite + TypeScript, scaffoldat med `npm create vite@latest -- --template react-ts`
- Vite dev-proxy (`/api` → backend) i dev, så frontend och backend ser ut som samma origin — inget CORS-krångel i den vanliga utvecklingsloopen
- CORS-middleware på backend (`app/config.py: cors_allowed_origins`) som komplement, för lägen där frontend inte går via Vites proxy (t.ex. en byggd statisk site)
- docker-compose-service `frontend`: produktionsbyggd image, inte volymmonterad källkod
  — multi-stage `Dockerfile` (`npm run build` → `nginx:alpine` serverar `dist/`),
  `nginx.conf` proxyar `/api/` till `app:8000` på compose-nätverket. Ingen
  live-reload i detta läge; `npm run dev` lokalt (Vite dev-proxy mot `localhost:8000`)
  är den snabba loopen för aktiv frontend-utveckling
- Huvudvy: sökbar/sorterbar/paginerad tabell över installationer (miljö, host/cluster,
  artefakt+version, källtyp, status, senast sedd) mot `GET /api/v1/installations`
- Sökfält (debounced 300ms), källtyp-filter, "visa borttagna"-toggle, klickbara
  sorterbara kolumnrubriker, statusbadges — designsystem via CSS custom properties
  med stöd för ljust/mörkt läge (`prefers-color-scheme`)
- Logga (`Logo.tsx` + `public/favicon.svg`): en öppen loggbok — mjuka, kurvade
  sidor (inte raka trapetser) i en blå→turkos gradientcirkel, med tunna
  "loggrader" och ett amber bokmärkesband som accent. Sidhuvudet
  (`.site-header`) har logga i vänsterhörnet, centrerad titel/undertitel i
  mitten (CSS-grid `auto 1fr auto`, tom spacer-div i tredje kolumnen för att
  balansera) och en gradientbakgrund + färgade källtyp-badges (rpm=amber,
  kubernetes=turkos) för mer färg utöver den neutrala tabellgrunden.
- Flikar (enkel state-switch, inget router-bibliotek): "Installationer" (huvudtabellen,
  med ett separat "Miljö"-fält som använder `environment`-filtret ovan —
  precist, till skillnad från det fria textsöket) och "Jämför miljöer"
  (`EnvironmentDiff.tsx`): två inmatningsfält (ingen källtyp-väljare) —
  visar **båda källtyperna samtidigt** (en `DiffResultSection` för RPM och en
  för Kubernetes, hämtade i parallell) så fort båda miljöfälten är ifyllda;
  tabell med vänster-/högerversion och statusbadge per artefakt mot
  `GET /environments/diff`
- KPI-rad (stat tiles, se dataviz-skillens mönster: label + semibold värde)
  överst på Installationer: aktiva totalt / RPM / Kubernetes / borttagna
- "Ta bort"-knapp per rad, bara på Installationer-fliken (Jämför miljöer är
  läs-only) — anropar `DELETE /api/v1/installations/{id}`, kräver en
  API-nyckel som anges i ett fält i verktygsraden och sparas i `localStorage`
- Badges: släta, mättade färger (vit text) — inte de bleka pastellfärgerna
  från första versionen — separata CSS-variabler för badge-färg (mättad) vs.
  diff-radernas bakgrundston (bleknad, för läsbarhet på hel rad)
- Blek vattenstämpel: en enda stor logbok-glyf (linjeversion av `Logo.tsx`,
  `.watermark` i `App.css`), `background-repeat: no-repeat`, delvis utanför
  kant i sidans nedre högra hörn, opacity ~0.03–0.05 — en diskret prägel,
  inte ett upprepat mönster, mot "vitt och tråkigt" bakgrund

*Klart när:* `npm run build` går grönt, `npm run dev` (lokalt eller via `docker compose up frontend`) visar en sida som hämtar och renderar riktig data från API:et, sökning/sortering/filter/paginering/miljö-bläddring/diff fungerar mot backend

*Klart när:* `uv run pytest` kör grönt, täcker happy path + felfall + minst ett konkurrensscenario per ingestion-mönster

## Begränsningar / Icke-mål
- Ingen fullständig tidsserie/point-in-time-historik ("vad var installerat den 3 mars") — endast `first_seen_at`/`last_seen_at`/`removed_at` per installation
- Ingen distribuerad låsning (Redis-lock etc.) i denna fas — enkel konflikt-avvisning per miljö räcker tills verkligt behov visar sig
- Ingen OAuth/roller — enkel API-nyckel per klientsystem
- Ingen skalningsoptimering utöver rimlig connection-pooling — optimera vid behov senare

## Beslutade svar på tidigare öppna frågor
1. Format: JSON genomgående, men olika scheman beroende på källsystem (inte olika filformat)
2. Kubernetes-komponent = container-image; miljö = namespace, kluster = separat `host_or_cluster`-fält
3. RPM-miljö identifieras via egen identifierare, men hostname sparas också i `host_or_cluster`
4. Borttagning: primärt via snapshot-diff, men manuell borttagnings-endpoint finns också
5. Snapshot är sanningskälla vid konflikt mot händelse-baserad data
6. Ingen distribuerad låsning nu — atomär upsert + enkel konflikt-avvisning per miljö räcker

## Kvarstående öppna frågor (bra att lösa innan kodning, men blockerar inte start)
- Exakt fältnamn/struktur i RPM- respektive Kubernetes-payloads (be om exempel-JSON om möjligt innan steg 3 påbörjas)
- Förväntad volym/frekvens av snapshots och händelser (påverkar dimensionering av connection pool och ev. framtida behov av kö/batch-bearbetning)
