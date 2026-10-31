# Protected account storage

Optional `storage_auth` requires [storage](storage.md), engine22/wire15, schema012.
The policy participates in the composite durable inventory identity. Existing
realms require an explicit migration; removing protection or changing definitions
fails startup even when credentials exist without a warehouse row.

Source fields are `minimum`, `maximum` (integers1..128, minimum<=maximum),
`comparison` (`exact` or `ascii-insensitive`), `alphabet`
(sorted unique printable ASCII33..126,1..94bytes), and `forbidden` (up to400 unique
case-insensitive substrings,1..64 printable ASCII bytes each). `storage-auth.bin`:
`N3K1`, u32 minimum/maximum/comparison (0exact,1ASCII insensitive), string alphabet, u32 word count, uppercase strings.
All readers reject malformed lengths/order/duplicates, unsupported versions and
unlisted files. An original fixture uses6..16bytes, letters/digits/`:;_`, and one
synthetic forbidden word, with ASCII-insensitive comparison. Credentials are
normalized only for the selected comparison mode before hashing. Raw request
verifiers retain exact request bytes, so changing case under an existing operation
ID is still a different request. This is package data, not engine-owned KO policy.

The selected character determines account/realm ownership. Status reveals only
credential disposition. Unlock and change require current session/realm/life,
alive simulation state, a package storage service and its access radius, and a
snapshot no older than two seconds at commit. A change verifies the old password,
validates the replacement, increments credential revision, and grants the initiating
session. Every warehouse read, transfer and historical retry checks the current
credential revision and that character's session/realm generations. Rotating the
credential revokes other characters' older grants; reconnect starts locked.

The durable worker reads a credential snapshot, releases its transaction, and hashes
on a blocking worker behind the existing two-permit password semaphore. scrypt
N131072/r8/p1, independent random16-byte salts,32-byte verifiers and constant-time
comparison match account-password work. No hashing blocks simulation or holds a
SQL lock. Credential CAS rejects an intervening rotation. Final transactions lock
credential before storage/character; all mutations also retain the realm fence.
The existing Redis password budget applies to a distinct warehouse account key
(10/minute) and the shared peer-IP budget(30/minute). Redis failure denies password
attempts; read-only status and ordinary world traffic continue.

Unlock/change IDs have immutable durable outcomes. The ledger stores a separate
salted **slow** request verifier over the domain, account-character context, realm,
service, operation and request fields. It never stores plaintext password fields or
an inexpensive password-verification digest. Exact retries return original status
and revision. `authorized_revision` is separately computed for the current session:
a historical success cannot unlock a later credential revision. A current successful
retry may regrant a reconnected session. Concurrent first requests sharing an ID
may receive `request_conflict`; retrying after the first commits resolves its
canonical verifier. Failed proofs are also immutable outcomes. Range/deadline and
format denials are not committed ledger entries.

Initialize a protected warehouse once using an operator terminal:

```bash
source tools/env.sh
read -rs -p 'Initial warehouse password: ' storage_password; echo
printf '%s\n' "$storage_password" | N3E_PACKAGE=/absolute/cooked/package \
  N3E_REALM=your-realm target/debug/n3e-server storage-password-init ACCOUNT
unset storage_password
```

`DATABASE_URL` must point to the intended migrated database. Provisioning refuses
to overwrite an existing verifier. It does not deploy or convert a live realm.
The supplied DB backup has no `strWarehousePW`; historical default/initial creation
is still unconfirmed. This explicit bootstrap is not a claimed KO default.

Native `/bankunlock` and `/bankpassword` open masked prompts; changes collect old,
new and confirmation. Escape clears the draft. `/bankauthretry` resends the last
request held only in process memory; reconnect clears it. Passwords never enter
chat. `/bankunlock SECRET` and `/bankpassword SECRET` discard the inline argument
and enter the masked prompt. The display is a reusable original dialog; complete
legacy keypad, drag/drop and regional layout fidelity remain open.

Binary evidence and demonstrated corrections are in the work record
and binary policy. This adds ordinary verify/change
and protected storage authorization, not complete KOF-0048 historical fidelity.
