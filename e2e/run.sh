#!/usr/bin/env sh
# Runs the local Podman E2E stack with a database volume unique to this project.
set -eu

compose_command=${PODMAN_COMPOSE_CMD:-podman-compose}
project_name=${E2E_PROJECT_NAME:-dynasty-dreams-e2e}
compose_file=docker-compose.e2e.yml

if ! command -v "$compose_command" >/dev/null 2>&1; then
  echo "Missing $compose_command. Install podman-compose or set PODMAN_COMPOSE_CMD." >&2
  exit 1
fi

compose() {
  "$compose_command" -p "$project_name" -f "$compose_file" "$@"
}

cleanup() {
  compose down --volumes --remove-orphans
}

cleanup
trap cleanup EXIT INT TERM
compose up --detach --build mongo backend web
compose run --rm --build e2e
