# Loggboken

*(repo-namnet är fortfarande `environment-inventory` — "Loggboken" är produktnamnet)*

Backend + frontend som tar emot och visar information om artefakter installerade i olika miljöer. Se `CLAUDE.md` för fullständig implementationsplan.

## Kom igång lokalt (docker-compose)

`docker compose up -d` (utan flaggor, standardprojektet) är **produktionslikt
och börjar helt tomt** — precis som en riktig instans skulle, innan någon
verklig ingestion skett. Den seedas aldrig automatiskt.

Kopiera `.env.example` till `.env` (gitignorad, `docker-compose.yml` läser den via `env_file`):

```bash
cp .env.example .env
docker compose up -d --build                 # bygger och startar appen + PostgreSQL, tomt
docker compose exec app alembic upgrade head  # kör migrationer
```

Servern svarar på `GET http://localhost:8000/api/v1/health` (kräver ingen nyckel).
`GET http://localhost:8000/api/v1/environments` ska ge `"total": 0` på en
nystartad instans — annars är den inte längre ren.

Databasen lagras i den namngivna volymen `postgres_data` och ligger kvar mellan
`docker compose down`/`up` (tas bara bort med `docker compose down -v`).

`docker compose up -d --build` startar även **frontend** på
`http://localhost:5173` — en produktionsbyggd image (`npm run build` → nginx
serverar det statiska resultatet och proxyar `/api/*` till backend-containern).
Inget live-reload här; kör `docker compose up -d --build frontend` igen efter
ändringar i `frontend/` för att bygga om imagen.

## Testa mot exempeldata

Vill du peta runt manuellt (t.ex. testa frontend-tabellen) utan att smutsa ner
den produktionslika instansen? Kör seed-scriptet mot en **egen, separat
instans** — Docker Compose isolerar helt (egen databas/volym/nätverk/containrar)
baserat på **projektnamn**, så samma `docker-compose.yml` räcker, ingen extra
compose-fil behövs:

```bash
docker compose -p loggboken-test up -d --build
docker compose -p loggboken-test exec app alembic upgrade head
docker compose -p loggboken-test exec app python -m scripts.seed
```

Kör den på egna portar om standardinstansen redan är igång samtidigt
(`docker-compose.yml` har fasta portmappningar 8000/5173/5432 — annars stäng
ner standardinstansen först med `docker compose down`). Städa bort helt med
`docker compose -p loggboken-test down -v`.

**Vad seedas:** tre RPM-miljöer (`proj1`, `proj2`, `prod`) och fyra
Kubernetes-projektgrupper (`proj1-*`, `proj2-*`, `proj3-*`, `prod-*`), bra
underlag för både miljö-prefix-bläddring och diff mellan miljöer. `prod`
körs dessutom på **två kluster** — `k821.prod` (huvud: `prod-frontend`,
`prod-backend`, `prod-worker`) och `k822.prod` (`prod-backend-k822`, samma
`api`-image+version som `prod-backend`) — för att visa att en och samma
artefakt kan vara installerad i flera kluster samtidigt, både i
installationstabellen och i "Jämför miljöer". `proj1`/`proj2`/`proj3` delar
klustret `k811.system`.

**Testdatabasen** (`--profile test`, tmpfs) är en tredje, separat sak — se
avsnittet "Tester" nedan. Den är till för `uv run pytest`, inte för manuell
utforskning.

## Frontend

React + Vite + TypeScript i `frontend/`, samma repo som backend (se `CLAUDE.md`
för resonemanget bakom det valet).

Två flikar:

- **Installationer** (`InstallationsTable.tsx`) — en KPI-rad överst (aktiva
  totalt / RPM / Kubernetes / borttagna), sökbar, sorterbar, paginerad
  tabell över alla installationer mot `GET /api/v1/installations`: fritextsök
  (miljö/host/artefakt, debounced), ett separat precist **"Miljö"-fält** (matchar
  exakt namn eller ett helt projektprefix, t.ex. `proj1` hittar alla
  `proj1-xxx`-namespaces), filter på källtyp, "visa borttagna"-toggle,
  klickbara sorterbara kolumner. Varje aktiv rad har en **"Ta bort"-knapp**
  (`DELETE /api/v1/installations/{id}`) — kräver en API-nyckel, angiven i
  fältet i verktygsraden och sparad i `localStorage` (bara på den här fliken;
  Jämför miljöer är läs-only). Kolumnerna radbryts aldrig, så tabellen kan bli
  bredare än fönstret — "Ta bort"-kolumnen är fastnålad i högerkanten
  (`position: sticky; right: 0`), så knappen alltid syns utan att behöva
  scrolla hela vägen till höger.
- **Jämför miljöer** (`EnvironmentDiff.tsx`) — två miljöer (eller
  projektprefix-grupper) sida vid sida mot `GET /environments/diff`. Hämtar
  **båda källtyperna samtidigt** (RPM och Kubernetes, i parallell) så fort
  båda fälten är ifyllda — ingen källtyp behöver väljas manuellt. Resultaten
  slås ihop till **en enda tabell** med en **"Typ"-kolumn** (källtyp-badge)
  längst till vänster istället för separata sektioner per källtyp, plus
  vänster-/högerversion per artefakt (miljönamn **och host/cluster**, t.ex.
  `1.5.0 (proj1-backend · k811.system)`) och en statusbadge (samma /
  olika version / bara vänster / bara höger).

Designsystemet ligger i `src/App.css` som CSS custom properties, med stöd för
både ljust och mörkt läge. Badges använder släta, mättade färger (vit text)
för status/källtyp/diff istället för bleka pastellfärger. Appens brand-tema
(header, fokusringar, aktiv flik, länkar/knappar) är Bolagsverkets faktiska
gult/blå-palett — det dominerande intrycket på bolagsverket.se är en ganska
**ljus** blå (deras kort-/listbakgrunder, inte en mörk marinblå yta), så
header-gradienten går från en medelblå (`--gradient-start: #1d5fa8`) till en
ljusare himmelsblå (`--gradient-end: #4f95d9`) med en guldkant
(`border-bottom: 3px solid #f6ca47`) under headern och guld (`#f6ca47`) som
accent på loggans ram/spänne/stjärna. `--color-accent` (länkar, fokusringar,
aktiv flik) är den mörkare länkblåa `#2a63b7`, och `--color-accent-bg`
(hover/paginering) är en blek blå kortbakgrund (`#d3e9f8`) — färgerna är
avlästa pixel för pixel ur en skärmdump av bolagsverket.se. Källtyp-/statusbadges (rpm=amber, kubernetes=turkos,
aktiv=grön osv.) är oberoende identitetsfärger och påverkas inte av bytet.
Loggan (`Logo.tsx` + `favicon.svg`) är en tiltad, sluten läderbunden loggbok
med rem, spänne och en guldstämplad stjärna — läder-/pergamentfärgerna på
själva bokillustrationen är kvar som en varm detalj mot den marinblå
cirkelbadgen. En blek, stor logbok-glyf ligger fixerad i bakgrundens nedre
högra hörn som en diskret vattenstämpel — en enda instans, inte ett upprepat
mönster. I headern sitter loggan i vänsterhörnet med titeln centrerad i mitten.

**Via docker-compose** (startas redan av `docker compose up -d --build` ovan):
produktionsimage (nginx), `http://localhost:5173`, proxyar `/api/*` till
backend-containern. Bygg om (`docker compose up -d --build frontend`) efter
källkodsändringar — ingen live-reload i det här läget.

**Fristående, utan Docker, med live-reload under utveckling:**

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxyar /api/* till http://localhost:8000
```

Kräver att backend redan kör på port 8000 (endera via `docker compose up -d app`
eller `uv run uvicorn app.main:app`). Det här är den snabbaste loopen för att
faktiskt jobba i frontend-koden — docker-compose-varianten är till för att
köra/testa hela stacken produktionslikt, inte för aktiv utveckling.

```bash
npm run build   # typkontroll + produktionsbygge till frontend/dist
```

## Autentisering

Endast **skrivande** endpoints (`POST /installations`, `POST .../snapshot`,
`DELETE /installations/{id}`) kräver en `X-API-Key`-header. **Läsning är
öppen** — `GET /environments`, `GET .../installations`, `GET
.../environments` (artifact-omvänd) och `/health` kräver ingen nyckel alls.
Det här är ett internt system, så gränsen sätts där den faktiskt spelar roll
(vem får skriva/ändra data) istället för att tvinga alla team som vill
scripta mot läs-endpoints att provisionera en nyckel först.

Nycklar konfigureras via `APP_API_KEYS` (JSON, se `.env` / `docker-compose.yml`)
och kan begränsas till specifika `source_types` — men bara för skrivning.
Dev-nycklar (redan uppsatta lokalt):

| Nyckel          | Klient         | Får skriva till |
|-----------------|----------------|-----------------|
| `dev-rpm-key`   | dev-rpm-agent  | `rpm`           |
| `dev-k8s-key`   | dev-k8s-agent  | `kubernetes`    |
| `dev-admin-key` | dev-admin      | alla            |

```bash
curl http://localhost:8000/api/v1/environments   # läsning: ingen nyckel behövs
```

Se **"Exempel på anrop mot API:et"** nedan för fullständiga exempel på skrivande anrop med `X-API-Key`.

## Exempel på anrop mot API:et

Alla exempel nedan använder dev-nycklarna från tabellen ovan.
`<environment_id>`/`<installation_id>`/`<artifact_id>` är UUID:er du får tillbaka
från tidigare anrop (t.ex. `environment_id` i svaret från ett `POST /installations`).

### Skicka in en installation (mönster A — händelsebaserad)

```bash
curl -X POST http://localhost:8000/api/v1/installations \
  -H "X-API-Key: dev-rpm-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "rpm",
    "data": {
      "host": "web-01.prod.example.com",
      "environment_name": "proj1",
      "packages": [
        {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"}
      ]
    }
  }'
```

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/installations",
    headers={"X-API-Key": "dev-rpm-key"},
    json={
        "source_type": "rpm",
        "data": {
            "host": "web-01.prod.example.com",
            "environment_name": "proj1",
            "packages": [
                {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
            ],
        },
    },
)
response.raise_for_status()
print(response.json())  # {"environment_id": "...", "upserted": 1}
```

### Skicka in en snapshot (mönster B — hela miljöns nuvarande state)

```bash
curl -X POST "http://localhost:8000/api/v1/environments/<environment_id>/snapshot" \
  -H "X-API-Key: dev-k8s-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "kubernetes",
    "data": {
      "namespace": "proj1-toolchain-exempel",
      "cluster": "k811.system",
      "pods": {
        "items": [
          {
            "metadata": {
              "name": "toolchain-7f9c9d-abc12",
              "annotations": {"kubectl.kubernetes.io/default-container": "toolchain"}
            },
            "spec": {
              "containers": [
                {"name": "toolchain", "image": "registry.example.com/proj1/toolchain:1.4.2"},
                {"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}
              ]
            }
          }
        ]
      }
    }
  }'
```

`pods` är rådatan från `kubectl get pods -n proj1-toolchain-exempel -o json` — samma
JSON-format rakt igenom, och stabilt mellan kubectl-versioner. `spec.initContainers`
läses aldrig. Sidecars som `istio-proxy` delar `spec.containers` med huvudcontainern
utan någon inbyggd k8s-flagga för det; finns annotationen
`kubectl.kubernetes.io/default-container` (satt av bl.a. Istios auto-injection)
litar parsern på den och tar bara den namngivna containern — `istio-proxy` ovan
filtreras alltså bort och bara `toolchain` blir en installation.

**Alternativ: rå `kubectl describe pods`-text.** Om källsystemet inte kan producera
JSON går det att skicka in rå textutdata från `kubectl describe pods -n <namespace>`
istället, via fältet `describe_output` — exakt ett av `pods`/`describe_output` måste
anges:

```bash
curl -X POST "http://localhost:8000/api/v1/environments/<environment_id>/snapshot" \
  -H "X-API-Key: dev-k8s-key" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c '
import json
describe_output = """Name:             toolchain-7f9c9d-abc12
Namespace:        proj1-toolchain-exempel
Annotations:      kubectl.kubernetes.io/default-container: toolchain
Containers:
  toolchain:
    Image:          registry.example.com/proj1/toolchain:1.4.2
  istio-proxy:
    Image:          istio/proxyv2:1.20.0
"""
print(json.dumps({
    "source_type": "kubernetes",
    "data": {
        "namespace": "proj1-toolchain-exempel",
        "cluster": "k811.system",
        "describe_output": describe_output,
    },
}))
')"
```

Konverteras internt (`app/parsers/kubectl_describe.py`) till samma interna Pod-form
som `pods`-varianten, så samma sidecar-/initcontainer-filtrering gäller. Kubectls
textlayout är dock kubectls egna människoläsbara format, inte en versionerad
kontrakt-yta som `-o json` är — använd `pods` när källsystemet kan producera JSON.

Svar: `{"environment_id": "...", "active": 1, "removed": 0}` — `removed` är antalet
artefakter som fanns i databasen men saknades i den inskickade listan.

**Genväg utan UUID:** miljö-ID:t är ett UUID, så för att snapshotta måste man
normalt först slå upp det (t.ex. spara `environment_id` från det första
händelse-baserade anropet, eller fråga `GET /environments`). Ett källsystem
som bara känner sitt eget namn (en nattlig cron för en specifik host/namespace)
kan istället adressera miljön direkt via namn + källtyp:

```bash
curl -X POST "http://localhost:8000/api/v1/environments/by-name/proj1-toolchain-exempel/snapshot?source_type=kubernetes" \
  -H "X-API-Key: dev-k8s-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "kubernetes",
    "data": {
      "namespace": "proj1-toolchain-exempel",
      "pods": {
        "items": [
          {
            "metadata": {"name": "toolchain-7f9c9d-abc12"},
            "spec": {"containers": [{"name": "toolchain", "image": "registry.example.com/proj1/toolchain:1.4.2"}]}
          }
        ]
      }
    }
  }'
```

Samma svar och samma diff-logik som UUID-varianten — `404 environment_not_found`
om ingen miljö med den kombinationen av `name`/`source_type` finns än (måste
skapas via ett första händelse-baserat anrop innan den kan snapshottas).

### Ta bort en installation manuellt (mönster C)

```bash
curl -X DELETE "http://localhost:8000/api/v1/installations/<installation_id>" \
  -H "X-API-Key: dev-admin-key"
```

### Läsa data

Läsning är öppen — ingen `X-API-Key` behövs:

```bash
curl "http://localhost:8000/api/v1/environments?source_type=rpm&limit=20"

curl "http://localhost:8000/api/v1/environments/<environment_id>/installations?include_removed=true"

# en specifik artefakt i en specifik miljö (via UUID)
curl "http://localhost:8000/api/v1/environments/<environment_id>/installations?artifact_name=openssl"

# samma sak, men via namn — inget UUID behöver slås upp först
curl "http://localhost:8000/api/v1/environments/by-name/proj1/installations?source_type=rpm&artifact_name=openssl"

curl "http://localhost:8000/api/v1/artifacts/<artifact_id>/environments"

# global sök över ALLA installationer (det frontendens tabell använder)
curl "http://localhost:8000/api/v1/installations?q=openssl&sort_by=artifact_name&sort_dir=asc"

# allt installerat "i en miljö" via bara namnet — för Kubernetes matchar detta
# ett helt projektprefix, t.ex. environment=proj1 hittar både namespace "proj1"
# och alla "proj1-xxx" (proj1-frontend, proj1-backend, ...)
curl "http://localhost:8000/api/v1/installations?environment=proj1"

# jämför två miljöer (eller projektprefix-grupper) sida vid sida
curl "http://localhost:8000/api/v1/environments/diff?left=proj1&right=proj2&source_type=kubernetes"
```

```javascript
// t.ex. från en framtida frontend, eller ett team-script — ingen nyckel krävs
const response = await fetch("http://localhost:8000/api/v1/environments");
const { items, total } = await response.json();
```

Fullständig, körbar API-referens (alla scheman och felkoder) finns på
`http://localhost:8000/docs` (Swagger UI, genereras automatiskt av FastAPI).

## Kom igång utan Docker (appen körs lokalt, bara PostgreSQL i Docker)

Det här är en aktiv utvecklingsloop, så kör mot den separata dev-instansen
(`-p loggboken-test`) — annars seedar du av misstag den produktionslika
standardinstansen igen:

```bash
docker compose -p loggboken-test up -d postgres
uv run alembic upgrade head
uv run python -m scripts.seed
uv run uvicorn app.main:app --reload
```

## Tester

Testerna är uppdelade i två helt separata kategorier:

- **`tests/unit/`** — inget nätverk, ingen databas, inga andra beroenden alls.
  Parsers, auth-logik (`require_api_key`/`check_source_type_access`),
  middleware (`MaxBodySizeMiddleware`) och ingestion-orkestreringen
  (`parse_or_record_failure`/`record_and_raise`) testas som ren Python-logik —
  databaskopplingen mockas bort (`unittest.mock.AsyncMock`) där en
  `asyncpg.Connection` annars hade behövts. Körs på under en sekund.
- **`tests/integration/`** — riktiga HTTP-anrop mot hela appen och en riktig
  PostgreSQL: ingestion (båda mönstren, inkl. diff-logiken), samtidighet,
  felhantering, query-endpoints. Detta är den enda kategorin som behöver en
  databas — och även den **kräver varken `docker-compose.yml` eller att
  appens Docker-image byggs**, bara en tom Postgres.

```bash
uv run pytest tests/unit          # inget extra behövs
uv run pytest tests/integration   # kräver en Postgres, se nedan
uv run pytest                     # båda
```

`tests/` och testberoenden (`pytest`, `httpx`, m.fl.) finns aldrig i
Docker-imagen: `.dockerignore` exkluderar `tests/`, och `Dockerfile` kör
`uv sync --no-dev` som hoppar över dev-dependency-gruppen. Bekräftat genom att
inspektera den byggda imagen — ingen `tests`-katalog, inget `pytest` i
`site-packages`.

### Köra integrationstester lokalt

De ska köras mot en engångsdatabas, inte mot den persistenta dev-databasen.
`tests/integration/conftest.py` vägrar köra om `APP_DATABASE_URL` pekar mot
port 5432 (dev-databasen) istället för 5433, så ett glömt `export` skriver
aldrig in testdata i dev-datat av misstag (skippas i CI, se nedan, där det
inte finns någon persistent databas att skydda).

**Via docker-compose** (`postgres-test`-servicen lagrar sin data i tmpfs/RAM
och startar bara via `--profile test`):

```bash
docker compose --profile test up -d postgres-test
export APP_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/environment_inventory
uv run alembic upgrade head
uv run pytest tests/integration
docker compose stop postgres-test   # kastar all testdata (tmpfs)
```

**Utan docker-compose** — vanlig `docker run` eller CI-plattformens inbyggda
Postgres-service fungerar precis lika bra:

```bash
docker run -d --name pg-test --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=environment_inventory -p 5433:5432 postgres:16-alpine

until docker exec pg-test pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done

export APP_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/environment_inventory
uv run alembic upgrade head
uv run pytest tests/integration

docker rm -f pg-test
```

### GitLab CI (`.gitlab-ci.yml`)

- **Varje push** (vilken branch som helst) och **varje merge request**: kör
  `unit-tests` — `tests/unit`, ingen databas startas alls.
- **Merge request mot `main`**: kör därutöver `integration-tests` — startar en
  disponibel `postgres:16-alpine`-service, kör migrationerna, kör
  `tests/integration`. Körs inte för MR:ar mot andra branches eller för vanliga
  branch-pushar, eftersom den är tyngre och till för grinden in mot `main`.
