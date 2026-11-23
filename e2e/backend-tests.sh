#!/usr/bin/env sh
# Runs the backend pytest suite inside the disposable Compose network.
# Invoked by the `pytest` service in docker-compose.e2e.yml; not meant to be run
# on a developer machine, where the guards below will refuse to continue.
#
# Why a copy: the suite hard-codes /app/backend, /app/frontend/src and
# /app/mobile/src (source-structure tests) and reads /app/frontend/.env. The
# repo is mounted read-only at $REPO_SRC and copied to $APP_DIR so the tests get
# that layout without writing into the host working tree.
set -eu

REPO_SRC=${REPO_SRC:-/repo}
APP_DIR=${APP_DIR:-/app}
RESULTS_DIR=${RESULTS_DIR:-/results}

die() { echo "backend-tests: $*" >&2; exit 1; }

# --- Isolation guards. The suite's conftest can delete Mongo data, so refuse
# --- to run unless every setting points at the disposable stack. These mirror
# --- tests/isolated_seed.py and are intentionally strict.
[ "${TEST_SUITE_ISOLATED:-}" = "1" ] || die "TEST_SUITE_ISOLATED must be 1"
[ "${SECURITY_TEST_ISOLATED:-}" = "1" ] || die "SECURITY_TEST_ISOLATED must be 1"
case "${MONGO_URL:-}" in
  mongodb://mongo:27017|mongodb://mongo:27017/) ;;
  *) die "MONGO_URL must be mongodb://mongo:27017 (got '${MONGO_URL:-}')" ;;
esac
[ "${DB_NAME:-}" = "dynasty_dreams_e2e" ] || die "DB_NAME must be dynasty_dreams_e2e"
[ "${REACT_APP_BACKEND_URL:-}" = "http://web" ] || die "REACT_APP_BACKEND_URL must be http://web"
[ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ] && [ -n "${JWT_SECRET:-}" ] \
  || die "ADMIN_EMAIL, ADMIN_PASSWORD and JWT_SECRET are required"
case "$APP_DIR" in
  ""|/|/home|/root|/usr|/etc|/var) die "refusing to use APP_DIR='$APP_DIR'" ;;
esac
[ -d "$REPO_SRC/backend/tests" ] || die "repo not mounted at $REPO_SRC"

# --- Build the /app layout the tests expect.
# The image ships the backend flattened into /app; replace it with the repo
# layout so /app/backend/... resolves.
mkdir -p "$APP_DIR"
find "$APP_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -C "$REPO_SRC" \
  --exclude=./.git --exclude=node_modules --exclude=__pycache__ \
  --exclude=./test-results --exclude='*.pyc' \
  -cf - . | tar -C "$APP_DIR" -xf -
mkdir -p "$APP_DIR/memory"
# Both .env files are gitignored, so absent from the repo, but a number of tests
# read them directly instead of using the environment. Values come from the
# guarded environment above, so they can only describe the disposable stack.
printf 'REACT_APP_BACKEND_URL=%s\n' "$REACT_APP_BACKEND_URL" > "$APP_DIR/frontend/.env"
{
  printf 'MONGO_URL=%s\n' "$MONGO_URL"
  printf 'DB_NAME=%s\n' "$DB_NAME"
  printf 'ADMIN_EMAIL=%s\n' "$ADMIN_EMAIL"
  printf 'ADMIN_PASSWORD=%s\n' "$ADMIN_PASSWORD"
  printf 'JWT_SECRET=%s\n' "$JWT_SECRET"
  printf 'REACT_APP_BACKEND_URL=%s\n' "$REACT_APP_BACKEND_URL"
} > "$APP_DIR/backend/.env"

# --- Wait for the API through the same path the tests use.
health_url="$REACT_APP_BACKEND_URL/api/health"
i=0
until python -c "import urllib.request,sys; urllib.request.urlopen(sys.argv[1], timeout=3)" "$health_url" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -le 60 ] || die "API not healthy at $health_url after 120s"
  sleep 2
done

# --- Run. Serial on purpose: tests share one database and sweep it between
# --- modules, so parallel workers would delete each other's fixtures.
cd "$APP_DIR/backend"
[ "$#" -gt 0 ] || set -- tests
mkdir -p "$RESULTS_DIR" 2>/dev/null || true
junit=""
[ -w "$RESULTS_DIR" ] && junit="--junitxml=$RESULTS_DIR/junit.xml"
# shellcheck disable=SC2086
exec python -m pytest -p no:cacheprovider -ra $junit "$@"
