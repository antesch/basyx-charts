#!/bin/sh
set -eu

schema_script="$(dirname "$0")/../../charts/basyx/files/wait-for-schema.sh"
test_root=$(mktemp -d)
trap 'rm -f "$test_root/count" "$test_root/log"; rmdir "$test_root"' EXIT HUP INT TERM

export POSTGRES_HOST=test-db POSTGRES_PORT=5432 POSTGRES_DBNAME=basyx
export POSTGRES_USER=basyx POSTGRES_PASSWORD=never-log-this-password
export POSTGRES_SSLMODE=verify-full POSTGRES_SSLROOTCERT=/certs/ca.crt
export POSTGRES_SEARCHPATH='tenant, public' POSTGRES_OPTIONS='-c lock_timeout=1000'
export EXPECTED_SCHEMA_VERSION=v1.2.3
export SCHEMA_WAIT_TIMEOUT_SECONDS=5 SCHEMA_WAIT_INTERVAL_SECONDS=1
export SCHEMA_CONNECT_TIMEOUT_SECONDS=2

# Deterministic clock and database responses exercise the shipped shell script.
date() { printf '%s\n' "$((100 + $(read_count)))"; }
sleep() { :; }
read_count() { read -r count < "$test_root/count"; printf '%s' "$count"; }
psql() {
  count=$(($(read_count) + 1))
  printf '%s\n' "$count" > "$test_root/count"
  [ "$PGHOST" = test-db ] && [ "$PGDATABASE" = basyx ] &&
    [ "$PGPASSWORD" = never-log-this-password ] &&
    [ "$PGSSLMODE" = verify-full ] && [ "$PGSSLROOTCERT" = /certs/ca.crt ] &&
    [ "$PGCONNECT_TIMEOUT" = 2 ] &&
    [ "$PGOPTIONS" = '-c lock_timeout=1000 -c statement_timeout=2000' ] || return 90
  sql=$(cat)
  case "$sql" in *"schema_search_path"*"FROM basyxsystem ORDER BY identifier"*) ;; *) return 91 ;; esac
  case "$mode" in
    ready) printf '%s\n' 'v1.2.3|clean' ;;
    delayed)
      case "$count" in
        1) echo 'database unavailable' >&2; return 1 ;;
        2) printf '%s\n' 'v1.2.2|clean' ;;
        3) printf '%s\n' 'v1.2.3|dirty' ;;
        *) printf '%s\n' 'v1.2.3|clean' ;;
      esac ;;
    wrong) printf '%s\n' 'v1.2.2|clean' ;;
    dirty) printf '%s\n' 'v1.2.3|dirty' ;;
    empty) : ;;
    unavailable) echo 'connection refused' >&2; return 1 ;;
  esac
}

for mode in ready delayed wrong dirty empty unavailable; do
  printf '0\n' > "$test_root/count"
  if ( . "$schema_script" ) > "$test_root/log" 2>&1; then
    status=0
  else
    status=$?
  fi
  case "$mode" in
    ready|delayed)
      [ "$status" -eq 0 ] || { cat "$test_root/log"; exit 1; }
      if [ "$mode" = delayed ]; then
        [ "$(read_count)" -eq 4 ] || exit 1
      fi ;;
    *)
      [ "$status" -eq 1 ] || { cat "$test_root/log"; exit 1; }
      grep -q 'Timed out waiting for clean schema' "$test_root/log" || exit 1 ;;
  esac
  if grep -q 'never-log-this-password' "$test_root/log"; then exit 1; fi
  printf 'PASS schema wait: %s\n' "$mode"
done
