set -eu

export PGHOST="${POSTGRES_HOST}" PGPORT="${POSTGRES_PORT}"
export PGDATABASE="${POSTGRES_DBNAME}" PGUSER="${POSTGRES_USER}"
export PGPASSWORD="${POSTGRES_PASSWORD}"
export PGSSLMODE="${POSTGRES_SSLMODE:-disable}"
export PGSSLCERT="${POSTGRES_SSLCERT:-}" PGSSLKEY="${POSTGRES_SSLKEY:-}"
export PGSSLROOTCERT="${POSTGRES_SSLROOTCERT:-}"
export PGCONNECT_TIMEOUT="${SCHEMA_CONNECT_TIMEOUT_SECONDS}"
export PGAPPNAME="${POSTGRES_APPLICATIONNAME:-basyx-schema-wait}"
export PGTZ="${POSTGRES_TIMEZONE:-UTC}"
export PGOPTIONS="${POSTGRES_OPTIONS:-} -c statement_timeout=$((SCHEMA_CONNECT_TIMEOUT_SECONDS * 1000))"

deadline=$(($(date +%s) + SCHEMA_WAIT_TIMEOUT_SECONDS))
while :; do
  if actual=$(psql -X -q -A -t -v ON_ERROR_STOP=1 \
    -v "schema_search_path=${POSTGRES_SEARCHPATH:-}" <<'SQL'
SELECT pg_catalog.set_config('search_path', COALESCE(NULLIF(:'schema_search_path', ''), pg_catalog.current_setting('search_path')), false) \g /dev/null
SELECT trim(schema_version) || '|' || trim(state) FROM basyxsystem ORDER BY identifier ASC LIMIT 1;
SQL
  ); then
    if [ "${actual}" = "${EXPECTED_SCHEMA_VERSION}|clean" ]; then
      echo "Database schema ${EXPECTED_SCHEMA_VERSION} is clean; starting runtime."
      exit 0
    fi
    echo "Waiting for clean schema ${EXPECTED_SCHEMA_VERSION}; found: ${actual:-no version row}"
  else
    echo "Waiting for database connectivity and schema initialization..."
  fi
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    echo "Timed out waiting for clean schema ${EXPECTED_SCHEMA_VERSION} at ${POSTGRES_HOST}:${POSTGRES_PORT}" >&2
    exit 1
  fi
  sleep "${SCHEMA_WAIT_INTERVAL_SECONDS}"
done
