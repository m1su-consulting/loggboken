# Loggboken på Kubernetes

Vanliga Kubernetes-manifest (ingen Helm) för att köra backend + frontend.
PostgreSQL körs **inte** i klustret — appen pekar mot en hanterad databas
(RDS, Cloud SQL, eller motsvarande) via `APP_DATABASE_URL` i `secret.yaml`.
Ingen Ingress är satt upp än — bara `ClusterIP`-Services; lägg till Ingress
(eller port-forward/NodePort) själva när klustrets nätverkslösning är känd.

## Förutsättningar

- En redan existerande, nåbar Postgres-instans (skapa databasen och kör
  migrationerna dit, se nedan — inget här skapar databasen åt dig).
- Images byggda och pushade till ett registry ni har tillgång till:
  - `docker build -t REGISTRY/loggboken-app:TAG .` (repo-roten, `Dockerfile`)
  - `docker build -t REGISTRY/loggboken-frontend:TAG frontend/` (`frontend/Dockerfile`)
  - Alla manifest nedan har `REGISTRY/loggboken-app:TAG` /
    `REGISTRY/loggboken-frontend:TAG` som platshållare — byt ut i
    `app-deployment.yaml`, `frontend-deployment.yaml` och `migration-job.yaml`
    (samma image+tag som app-deployment.yaml).
  - `.gitlab-ci.yml` bygger/testar men push:ar **inte** images till ett
    registry än — det är ett rimligt nästa steg om ni vill automatisera det.

## Filer

| Fil | Vad |
|---|---|
| `namespace.yaml` | Skapar namespace `loggboken` |
| `configmap.yaml` | Icke-känslig config (CORS-origins, connection-pool-storlek, request-body-gräns) |
| `secret.example.yaml` | **Mall** — kopiera till `secret.yaml` (gitignorad), fyll i `APP_DATABASE_URL` + `APP_API_KEYS` |
| `migration-job.yaml` | Engångs-`Job` som kör `alembic upgrade head` mot databasen |
| `app-deployment.yaml` | Backend (FastAPI/uvicorn), 2 repliker, readiness/liveness mot `/api/v1/health` |
| `app-service.yaml` | `ClusterIP`-Service **namngiven `app`** — se kommentar i filen för varför |
| `frontend-deployment.yaml` | Frontend (nginx + byggd React-app), 2 repliker |
| `frontend-service.yaml` | `ClusterIP`-Service för frontend |

## Deploy, i ordning

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml

cp k8s/secret.example.yaml k8s/secret.yaml
# redigera k8s/secret.yaml med riktiga värden, byt sedan `kind: Secret`-namnet
# är redan rätt (loggboken-secrets) — bara värdena ska ändras
kubectl apply -f k8s/secret.yaml

# migrera databasen INNAN appen startar, första gången och vid varje ny
# migration i en senare image-version
kubectl apply -f k8s/migration-job.yaml
kubectl wait --for=condition=complete --timeout=120s job/loggboken-migrate -n loggboken
kubectl delete job/loggboken-migrate -n loggboken   # Jobs rensar inte sig själva

kubectl apply -f k8s/app-deployment.yaml
kubectl apply -f k8s/app-service.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/frontend-service.yaml
```

Kontrollera:

```bash
kubectl get pods -n loggboken
kubectl port-forward -n loggboken svc/loggboken-frontend 8080:80
# öppna http://localhost:8080
```

## Testa lokalt med Docker Desktop

Docker Desktop på Mac har ett inbyggt enkel-nod-kluster (Settings → Kubernetes
→ Enable Kubernetes). Images byggda lokalt med `docker build` är direkt
synliga för det klustret via samma image-store — inget registry behövs.
`REGISTRY/...:TAG`-platshållarna i manifesten byts ut mot en lokal tagg med
`sed` vid apply-tillfället (ingen extra fil eller kustomize-beroende); eftersom
taggen inte är `latest` blir Kubernetes default-`imagePullPolicy`
(`IfNotPresent`) redan rätt — den drar aldrig utifrån om imagen redan finns
lokalt.

```bash
kubectl config use-context docker-desktop

docker build -t loggboken-app:local .
docker build -t loggboken-frontend:local frontend/

# Databas: kör den befintliga docker-compose-postgresen (inget här skapar en
# databas åt dig). host.docker.internal är Docker Desktops namn för "din Mac"
# sett inifrån klustret.
docker compose up -d postgres

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml

cp k8s/secret.example.yaml k8s/secret.yaml
# redigera k8s/secret.yaml:
#   APP_DATABASE_URL: postgresql://postgres:postgres@host.docker.internal:5432/environment_inventory
kubectl apply -f k8s/secret.yaml

sed 's#REGISTRY/loggboken-app:TAG#loggboken-app:local#' k8s/migration-job.yaml | kubectl apply -f -
kubectl wait --for=condition=complete --timeout=120s job/loggboken-migrate -n loggboken
kubectl delete job/loggboken-migrate -n loggboken

sed 's#REGISTRY/loggboken-app:TAG#loggboken-app:local#' k8s/app-deployment.yaml | kubectl apply -f -
kubectl apply -f k8s/app-service.yaml
sed 's#REGISTRY/loggboken-frontend:TAG#loggboken-frontend:local#' k8s/frontend-deployment.yaml | kubectl apply -f -
kubectl apply -f k8s/frontend-service.yaml

kubectl get pods -n loggboken
kubectl port-forward -n loggboken svc/loggboken-frontend 8080:80
# öppna http://localhost:8080
```

Vid ändringar i koden: bygg om imagen med samma tagg
(`docker build -t loggboken-app:local .`) och kör
`kubectl rollout restart deployment/loggboken-app -n loggboken` — Kubernetes
cachar annars podden på samma image-ID.

## Varför ingen `initContainer` för migrationer

Med flera repliker (`app-deployment.yaml` kör 2) skulle varje pod försöka
köra `alembic upgrade head` samtidigt vid en `initContainer`-lösning — alembic
har ingen inbyggd låsning mot det. Ett separat engångs-`Job`, körd innan
`app-deployment.yaml` appliceras/uppdateras, undviker racet helt.

## Kvarstående (medvetet inte byggt än)

- **Ingress** — inget hostname/TLS/ingress-klass är känt ännu (se
  ovan — bara `ClusterIP` tills vidare).
- **Image-publicering i CI** — `.gitlab-ci.yml` bygger/testar men push:ar
  inte till ett registry; naturligt nästa steg om ni vill att `kubectl apply`
  ska kunna peka på en CI-byggd tagg istället för en manuellt byggd image.
- **Secrets-hantering** — `secret.yaml` hanteras för hand här. Överväg Sealed
  Secrets eller External Secrets Operator om ni vill checka in något
  krypterat i Git istället för att hantera filen manuellt per kluster.
- **HorizontalPodAutoscaler** — inte satt upp, `replicas: 2` är statiskt.
