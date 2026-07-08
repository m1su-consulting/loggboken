# Loggboken — API-referens för Backstage-pluginen

Det här dokumentet innehåller *bara* det en Backstage-plugin behöver för att
prata med Loggbokens API. Fullständig implementationsplan för själva Loggboken-appen
finns i `CLAUDE.md` i det repot — den behövs inte här.

## Vad är Loggboken?

Backend + frontend som håller reda på vilka artefakter (RPM-paket,
container-images) som är installerade i vilka miljöer, just nu och historiskt.
Två källsystem: `rpm` och `kubernetes`.

## Basadress

`<FYLL I: URL till den Loggboken-instans pluginen ska prata med>`

## Autentisering

**Läsning kräver ingen `X-API-Key`.** Alla `GET`-endpoints nedan är öppna —
pluginen kan anropa dem direkt från frontend utan någon nyckel eller
backend-proxy. (Skrivande endpoints kräver nyckel, men är inte relevanta för
en Backstage-plugin som bara ska visa data.)

CORS: Backstage-appens origin måste läggas till i Loggbokens
`APP_CORS_ALLOWED_ORIGINS`-konfiguration innan pluginen kan anropa API:et
direkt från webbläsaren. Hör av dig till Loggboken-teamet med er Backstage-URL.

## Datamodell (kort version)

- **environment** — en miljö: `name` (logisk identifierare, t.ex. namespace
  eller RPM-källans egen ID), `source_type` (`rpm` | `kubernetes`),
  `host_or_cluster` (hostname respektive klusternamn)
- **artifact** — en artefakt: `name` + `version`, unik per `(name, version,
  source_type)`
- **installation** — kopplingen mellan en environment och en artifact:
  `status` (`active` | `removed`), `first_seen_at`, `last_seen_at`,
  `removed_at`

## Rekommenderad koppling: catalog-annotation → Loggboken-miljö

Lägg en annotation i varje tjänsts `catalog-info.yaml` som pekar ut vilken
Loggboken-miljö den motsvarar, t.ex.:

```yaml
metadata:
  annotations:
    loggboken.io/environment-name: proj1
    loggboken.io/source-type: rpm
```

Pluginen läser de två värdena och anropar endpointen nedan — inget UUID
behöver slås upp eller cachas.

## Endpoints att använda

### Installationer för en specifik entitet (huvudanvändningsfallet)

```
GET /api/v1/environments/by-name/{name}/installations?source_type=...
```

Query-parametrar (alla valfria utom `source_type`):
- `source_type` (krävs) — `rpm` | `kubernetes`
- `artifact_name` — exakt match, om du bara vill slå upp en specifik artefakt
- `include_removed` — `true` för att även få historik (borttagna)
- `limit` / `offset` — paginering (default 50, max 200)

Svar (`InstallationListResponse`):

```json
{
  "items": [
    {
      "id": "uuid",
      "environment_id": "uuid",
      "artifact_id": "uuid",
      "artifact_name": "openssl",
      "artifact_version": "3.0.7-1.el9.x86_64",
      "first_seen_at": "2026-07-07T17:39:01.922360Z",
      "last_seen_at": "2026-07-07T19:23:05.470067Z",
      "removed_at": null,
      "status": "active",
      "source_of_removal": null
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

404 (`{"error": "environment_not_found", "detail": "..."}`) om `name` +
`source_type` inte matchar någon miljö — dvs. entiteten har inte skickat in
någon data till Loggboken än.

### Global sök (om pluginen vill visa en bredare vy, t.ex. en översiktssida)

```
GET /api/v1/installations?q=...&source_type=...&include_removed=...&sort_by=...&sort_dir=...
```

- `q` — fritextsök över miljönamn, host/cluster och artefaktnamn samtidigt
- `sort_by` — `environment_name` | `host_or_cluster` | `artifact_name` |
  `artifact_version` | `status` | `first_seen_at` | `last_seen_at`
- `sort_dir` — `asc` | `desc`

Svar (`InstallationSearchListResponse`) — samma fält som ovan plus
`environment_name`, `host_or_cluster` och `source_type` inbakat i varje rad
(praktiskt när resultatet spänner över flera miljöer):

```json
{
  "items": [
    {
      "id": "uuid",
      "environment_id": "uuid",
      "environment_name": "proj1",
      "host_or_cluster": "proj1.example.com",
      "source_type": "rpm",
      "artifact_id": "uuid",
      "artifact_name": "openssl",
      "artifact_version": "3.0.7-1.el9.x86_64",
      "status": "active",
      "first_seen_at": "2026-07-07T17:39:01.922360Z",
      "last_seen_at": "2026-07-07T19:23:05.470067Z",
      "removed_at": null,
      "source_of_removal": null
    }
  ],
  "total": 3,
  "limit": 50,
  "offset": 0
}
```

### Omvänd fråga: var finns en viss artefakt

```
GET /api/v1/artifacts/{artifact_id}/environments
```

Kräver ett `artifact_id` (UUID) — hämta det från ett av fälten ovan
(`artifact_id`). Svarar med vilka miljöer artefakten finns/har funnits i.

## Facit vid osäkerhet

Full, alltid uppdaterad OpenAPI-spec: `<bas-adress>/openapi.json`, interaktiv
Swagger UI på `<bas-adress>/docs`. Om något i det här dokumentet skulle
skilja sig från specen är specen rätt.
