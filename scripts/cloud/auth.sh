# Shared Cursor Cloud Agents API auth + HTTP helper.
# Source from Extra High launch/list/status/watch/followup scripts.
# Never print API keys. Safe to source more than once.

cloud_api_base() {
  local base="${CURSOR_API_BASE:-https://api.cursor.com}"
  printf '%s\n' "${base%/}"
}

cloud_agent_env_path() {
  printf '%s\n' "${CURSOR_AGENT_ENV:-${HOME}/.config/cursor/agent.env}"
}

cloud_load_auth() {
  local restore=0
  case "$-" in *x*) restore=1; set +x ;; esac
  if [[ -z "${CURSOR_API_KEY:-}" ]]; then
    local env_file
    env_file="$(cloud_agent_env_path)"
    if [[ -f "$env_file" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$env_file"
      set +a
    fi
  fi
  if [[ "$restore" -eq 1 ]]; then set -x; fi
  if [[ -z "${CURSOR_API_KEY:-}" ]]; then
    return 1
  fi
  return 0
}

cloud_redact_stream() {
  python3 -c '
import os, sys
key = os.environ.get("CURSOR_API_KEY") or ""
text = sys.stdin.read()
if key:
    text = text.replace(key, "<redacted>")
sys.stdout.write(text)
'
}

cloud_json_get() {
  local file="$1"
  local dotted="$2"
  python3 -c '
import json, sys
path = sys.argv[2].split(".")
with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
for part in path:
    if isinstance(data, dict):
        data = data.get(part)
    else:
        data = None
        break
if data is None:
    print("")
elif isinstance(data, (dict, list, bool)):
    print(json.dumps(data))
else:
    print(data)
' "$file" "$dotted"
}

cloud_http_is_create_ok() {
  [[ "${CLOUD_HTTP_CODE:-}" == "200" || "${CLOUD_HTTP_CODE:-}" == "201" ]]
}

cloud_http_is_2xx() {
  [[ "${CLOUD_HTTP_CODE:-}" =~ ^2[0-9][0-9]$ ]]
}

# Sets CLOUD_HTTP_CODE and CLOUD_HTTP_BODY (temp file with response bytes).
# Extra args are passed to curl (headers, --data-binary, ...).
cloud_http_request() {
  local method="$1"
  local path="$2"
  shift 2
  cloud_load_auth || return 1
  local base restore=0 curl_ec=0 errfile
  base="$(cloud_api_base)"
  case "$-" in *x*) restore=1; set +x ;; esac
  if [[ -n "${CLOUD_HTTP_BODY:-}" && -f "${CLOUD_HTTP_BODY}" ]]; then
    rm -f "$CLOUD_HTTP_BODY"
  fi
  CLOUD_HTTP_BODY="$(mktemp "${TMPDIR:-/tmp}/cloud-http.XXXXXX")"
  errfile="$(mktemp "${TMPDIR:-/tmp}/cloud-http-err.XXXXXX")"
  set +e
  CLOUD_HTTP_CODE="$(
    curl -sS \
      --connect-timeout "${CLOUD_CURL_CONNECT_TIMEOUT:-30}" \
      --max-time "${CLOUD_CURL_MAX_TIME:-120}" \
      -o "$CLOUD_HTTP_BODY" \
      -w "%{http_code}" \
      --user "${CURSOR_API_KEY}:" \
      -X "$method" \
      -H "Accept: application/json" \
      "${base}${path}" \
      "$@" 2>"$errfile"
  )"
  curl_ec=$?
  set -e
  if [[ -s "$errfile" ]]; then
    cloud_redact_stream <"$errfile" >&2
  fi
  rm -f "$errfile"
  if [[ "$restore" -eq 1 ]]; then set -x; fi
  if [[ -z "${CLOUD_HTTP_CODE:-}" ]]; then
    CLOUD_HTTP_CODE="000"
  fi
  if [[ "$curl_ec" -ne 0 ]]; then
    return "$curl_ec"
  fi
  return 0
}
