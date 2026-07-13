#!/bin/bash
set -eo pipefail

BASE_URL=${1:-"http://localhost:8000"}

echo "Waiting for deployment at $BASE_URL to become ready..."
ready_passed=false
for i in $(seq 1 15); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/ready" || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "Readiness check passed on attempt $i"
    ready_passed=true
    break
  fi
  echo "Attempt $i: status $STATUS, waiting 2s..."
  sleep 2
done

if [ "$ready_passed" = "false" ]; then
  echo "Readiness check failed after 15 attempts"
  exit 1
fi

# Smoke tests
echo "Running smoke tests against $BASE_URL..."
LIVE=$(curl -s "$BASE_URL/live")
echo "Live response: $LIVE"
if [[ "$LIVE" != *"\"ok\":true"* ]]; then
  echo "Liveness check response invalid"
  exit 1
fi

READY=$(curl -s "$BASE_URL/ready")
echo "Ready response: $READY"
if [[ "$READY" != *"\"database\":\"connected\""* || "$READY" != *"\"cache\":\"connected\""* ]]; then
  echo "Readiness check response invalid"
  exit 1
fi

METRICS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/metrics")
if [ "$METRICS_STATUS" != "200" ]; then
  echo "Metrics endpoint returned $METRICS_STATUS, expected 200"
  exit 1
fi

# Business Smoke Check
echo "Running business smoke check..."
CREATE_RES=$(curl -s -X POST "$BASE_URL/v1/links/" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: API_KEY_A" \
  -d '{"long_url": "https://www.example.com"}')

LINK_CODE=$(echo "$CREATE_RES" | grep -o '"code":"[^"]*' | head -n 1 | cut -d'"' -f4)
LINK_ID=$(echo "$CREATE_RES" | grep -o '"id":[^,]*' | head -n 1 | cut -d':' -f2)

if [ -z "$LINK_CODE" ]; then
  echo "Failed to create link during smoke check: $CREATE_RES"
  exit 1
fi
echo "Created temporary link with code: $LINK_CODE, id: $LINK_ID"

# Redirect check
REDIRECT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/r/$LINK_CODE")
if [ "$REDIRECT_STATUS" != "302" ]; then
  echo "Redirect check failed: status $REDIRECT_STATUS, expected 302"
  exit 1
fi
echo "Redirect check passed (302 Found)"

# Cleanup check
DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/v1/links/$LINK_ID" \
  -H "X-API-Key: API_KEY_A")
if [ "$DELETE_STATUS" != "200" ]; then
  echo "Cleanup check failed: status $DELETE_STATUS, expected 200"
  exit 1
fi
echo "Cleanup check passed (200 OK)"

echo "All deployment verification checks passed successfully!"
exit 0
