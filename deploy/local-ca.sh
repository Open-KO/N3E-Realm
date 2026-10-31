#!/usr/bin/env bash
# Local development CA and localhost server certificate (git-ignored, never
# committed). A valid pair is verified and left untouched. PQ-295: a pair that is
# missing, unreadable, mismatched, expired or within RENEW_SECONDS of expiry is
# replaced in place by a new CA and server certificate, so `make live` (whose
# prepare runs this) never fails at prepare with "certificate has expired".
set -euo pipefail
cd "$(dirname "$0")/.."
local_dir="${1:-deploy/local}"
DAYS=30
# Renew when less than 7 days remain: longer than any live run or gate, and a
# persistent play stack started before the renewal keeps a week of validity.
RENEW_SECONDS=$((7 * 24 * 3600))
mkdir -p "$local_dir"

# One run at a time per directory (two make live prepares, a launcher).
if command -v flock >/dev/null; then
  exec 9>"$local_dir/.lock"
  flock 9
fi

# The reason the pair in $1 needs renewal, or nothing when it is valid. Reads
# public material only; key files are compared through their public keys.
renew_reason() {
  local d="$1" f
  for f in ca.pem server.pem server.key; do
    test -s "$d/$f" || { echo "missing $f"; return; }
  done
  for f in ca.pem server.pem; do
    if ! openssl x509 -noout -in "$d/$f" 2>/dev/null; then
      echo "unreadable $f"; return
    fi
    if ! openssl x509 -noout -checkend "$RENEW_SECONDS" -in "$d/$f" >/dev/null 2>&1; then
      echo "$f expired or expires within $((RENEW_SECONDS / 86400)) days"; return
    fi
  done
  if ! openssl verify -purpose sslserver -verify_hostname localhost -CAfile "$d/ca.pem" "$d/server.pem" >/dev/null 2>&1; then
    echo "server.pem does not verify against ca.pem"; return
  fi
  local cert_key key_pub
  cert_key="$(openssl x509 -noout -pubkey -in "$d/server.pem" 2>/dev/null)" || { echo "server.pem has no public key"; return; }
  key_pub="$(openssl pkey -pubout -in "$d/server.key" 2>/dev/null)" || { echo "unreadable server.key"; return; }
  test "$cert_key" = "$key_pub" || echo "server.key does not match server.pem"
}

reason="$(renew_reason "$local_dir")"
if test -n "$reason"; then
  echo "local-ca: renewing $local_dir ($reason)" >&2
  umask 077
  work="$(mktemp -d "$local_dir/.renew.XXXXXX")"
  trap 'rm -rf "$work"' EXIT
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$work/ca.key" -out "$work/ca.pem" -days "$DAYS" -subj '/CN=n3e local development CA' -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
  openssl req -newkey rsa:2048 -nodes -keyout "$work/server.key" -out "$work/server.csr" -subj '/CN=localhost'
  cat > "$work/extensions" <<'EXT'
subjectAltName=DNS:localhost
extendedKeyUsage=serverAuth
keyUsage=critical,digitalSignature,keyEncipherment
basicConstraints=critical,CA:FALSE
EXT
  openssl x509 -req -in "$work/server.csr" -CA "$work/ca.pem" -CAkey "$work/ca.key" -CAcreateserial -out "$work/server.pem" -days "$DAYS" -extfile "$work/extensions"
  chmod 644 "$work/server.pem" "$work/ca.pem"
  reason="$(renew_reason "$work")"
  test -z "$reason" || { echo "local-ca: new pair invalid ($reason)" >&2; exit 1; }
  # Same file system, so each rename is atomic. A reader between two renames can
  # still see a mixed pair; runs of this script wait on the lock above.
  for f in ca.key ca.pem server.key server.pem; do
    mv -f "$work/$f" "$local_dir/$f"
  done
  rm -f "$local_dir/server.csr" "$local_dir/extensions" "$local_dir/ca.srl"
fi
openssl verify -purpose sslserver -verify_hostname localhost -CAfile "$local_dir/ca.pem" "$local_dir/server.pem"
