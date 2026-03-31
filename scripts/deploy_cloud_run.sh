#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-asia-northeast3}"
SERVICE_NAME="${SERVICE_NAME:-database-llm-app}"
IMAGE_NAME="${IMAGE_NAME:-gcr.io/${PROJECT_ID}/${SERVICE_NAME}}"
CONNECTOR_NAME="${CONNECTOR_NAME:-}"
EGRESS_SETTING="${EGRESS_SETTING:-all-traffic}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required."
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is not installed."
  exit 1
fi

pushd "$(dirname "$0")/.." >/dev/null

gcloud config set project "${PROJECT_ID}"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud builds submit --tag "${IMAGE_NAME}" .

DEPLOY_ARGS=(
  run deploy "${SERVICE_NAME}"
  --image "${IMAGE_NAME}"
  --region "${REGION}"
  --platform managed
  --port 8080
  --set-env-vars "APP_ENV=prod,APP_PORT=8080"
)

if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  DEPLOY_ARGS+=(--allow-unauthenticated)
fi

if [[ -n "${CONNECTOR_NAME}" ]]; then
  DEPLOY_ARGS+=(--vpc-connector "${CONNECTOR_NAME}")
  DEPLOY_ARGS+=(--vpc-egress "${EGRESS_SETTING}")
fi

gcloud "${DEPLOY_ARGS[@]}"

popd >/dev/null

