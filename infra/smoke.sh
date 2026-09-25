#!/usr/bin/env bash
# End-to-end CRUD check against a running deployment.
#   ./infra/smoke.sh https://<function-app-host>
set -euo pipefail

BASE="${1:?usage: ./infra/smoke.sh <base-url>}"
BASE="${BASE%/}"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT
STATUS=""

call() {  # <method> <path> [json-body]
  local args=(-sS -o "$BODY" -w '%{http_code}' -X "$1")
  [[ $# -ge 3 ]] && args+=(-H 'content-type: application/json' -d "$3")
  STATUS="$(curl "${args[@]}" "$BASE$2")"
}

expect() {  # <status> <label>
  [[ "$STATUS" == "$1" ]] || { echo "FAIL $2: expected $1, got $STATUS: $(cat "$BODY")" >&2; exit 1; }
  echo "ok   $2 ($STATUS)"
}

field() {  # <key> -> value of that key in the JSON body
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$BODY" "$1"
}

check() {  # <condition-description> <actual> <expected>
  [[ "$2" == "$3" ]] || { echo "FAIL $1: expected '$3', got '$2'" >&2; exit 1; }
  echo "ok   $1"
}

call GET /api/health;                            expect 200 "health"
check "database configured" "$(field database)" "configured"

call POST /api/items '{"name": "smoke-test", "price": 1.5}'; expect 201 "create"
ID="$(field id)"

call GET "/api/items/$ID";                       expect 200 "get"
check "name round-trips" "$(field name)" "smoke-test"

call GET "/api/items?limit=100";                 expect 200 "list"
check "list contains item" \
  "$(python3 -c 'import json, sys; print(any(i["id"] == sys.argv[2] for i in json.load(open(sys.argv[1]))))' "$BODY" "$ID")" "True"

call PATCH "/api/items/$ID" '{"price": 2}';      expect 200 "patch"
check "price updated" "$(field price)" "2.0"

call DELETE "/api/items/$ID";                    expect 204 "delete"
call GET "/api/items/$ID";                       expect 404 "get after delete"

echo "Smoke test passed against $BASE"
