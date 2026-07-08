#!/usr/bin/env bash
# Exempel: hämta en snapshot av ALLA Kubernetes-namespace som matchar ett
# miljö-prefix (t.ex. PREFIX=proj1 -> namespacet "proj1" och alla
# "proj1-*", som "proj1-frontend"/"proj1-backend") och skicka in dem till
# Loggboken. Samma prefix-gränsdragning som appens eget `environment`-filter
# (exakt namn eller "<prefix>-"-gruppering, inte vilken substräng som helst
# — "proj10-other" matchar alltså INTE PREFIX=proj1).
#
# Kör en gång per kluster: KUBE_CONTEXT väljer kubeconfig-kontext, så samma
# script kan pekas mot olika kluster utan ändring. Klusternamnet
# (host_or_cluster) hämtas automatiskt ur kubeconfig — sätt CLUSTER manuellt
# bara om du vill visa ett annat namn än det kubeconfig faktiskt anger.
# Tänkt att köras periodiskt (t.ex. cron/CronJob).
#
# Beroenden: kubectl (mot rätt kubeconfig), jq, curl.
#
# Användning:
#   PREFIX=proj1 KUBE_CONTEXT=k811.system API_KEY=dev-k8s-key \
#     ./scripts/examples/kubernetes_snapshot.sh

set -euo pipefail

PREFIX="${PREFIX:?sätt PREFIX, t.ex. proj1 (matchar 'proj1' och alla 'proj1-*')}"
KUBE_CONTEXT="${KUBE_CONTEXT:-}"
API_URL="${API_URL:-http://localhost:8000/api/v1}"
API_KEY="${API_KEY:?sätt API_KEY (en nyckel med source_types som tillåter kubernetes)}"

kubectl_args=()
if [ -n "$KUBE_CONTEXT" ]; then
  kubectl_args=(--context "$KUBE_CONTEXT")
fi

# CLUSTER hämtas automatiskt ur kubeconfig (kontextens "cluster"-fält) om den
# inte redan är satt — kubeconfig vet redan vilket kluster det är, så det är
# sällan nödvändigt att ange CLUSTER manuellt. Sätt CLUSTER explicit bara om
# du vill visa ett annat/snyggare namn än det som faktiskt står i kubeconfig.
CLUSTER="${CLUSTER:-}"
if [ -z "$CLUSTER" ]; then
  CLUSTER="$(kubectl "${kubectl_args[@]}" config view --minify -o jsonpath='{.contexts[0].context.cluster}' 2>/dev/null || true)"
fi

namespaces=()
while IFS= read -r ns; do
  namespaces+=("$ns")
done < <(
  kubectl "${kubectl_args[@]}" get namespaces -o json \
    | jq -r --arg prefix "$PREFIX" \
        '.items[].metadata.name | select(. == $prefix or startswith($prefix + "-"))'
)

if [ "${#namespaces[@]}" -eq 0 ]; then
  echo "Inga namespace matchade prefixet '$PREFIX'" >&2
  exit 1
fi

echo "Matchande namespace (${#namespaces[@]} st): ${namespaces[*]}" >&2

snapshot_namespace() {
  local namespace="$1"
  local pods_json payload response http_status body

  pods_json="$(kubectl "${kubectl_args[@]}" get pods -n "$namespace" -o json)"

  payload="$(jq -n \
    --arg namespace "$namespace" \
    --arg cluster "$CLUSTER" \
    --argjson pods "$pods_json" \
    '{
      source_type: "kubernetes",
      data: (
        {namespace: $namespace, pods: $pods}
        + (if $cluster != "" then {cluster: $cluster} else {} end)
      )
    }')"

  do_snapshot() {
    curl -sS -w '\n%{http_code}' -X POST \
      "$API_URL/environments/by-name/$namespace/snapshot?source_type=kubernetes" \
      -H "X-API-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "$payload"
  }

  response="$(do_snapshot)"
  http_status="${response##*$'\n'}"
  body="${response%$'\n'*}"

  if [ "$http_status" = "404" ]; then
    # Miljön finns inte än — snapshot-endpointen skapar den inte åt dig.
    # Bootstrappa den med ett engångs händelse-baserat anrop (samma parser,
    # samma payload — skillnaden är bara att den här endpointen gör
    # get-or-create på miljön) och kör sedan snapshotten igen.
    echo "Miljön '$namespace' fanns inte — bootstrappar den först." >&2
    curl -sS -f -X POST "$API_URL/installations" \
      -H "X-API-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "$payload" >/dev/null
    response="$(do_snapshot)"
    http_status="${response##*$'\n'}"
    body="${response%$'\n'*}"
  fi

  echo "[$namespace] $body"
  if [ "$http_status" -ge 400 ]; then
    echo "[$namespace] Snapshot misslyckades (HTTP $http_status)" >&2
    return 1
  fi
}

failures=0
for namespace in "${namespaces[@]}"; do
  snapshot_namespace "$namespace" || failures=$((failures + 1))
done

if [ "$failures" -gt 0 ]; then
  echo "$failures av ${#namespaces[@]} namespace misslyckades" >&2
  exit 1
fi
