# MineTrace Field App (Flutter, offline-first)

The **Flutter offline-first field application** from the SIH abstract: foremen
capture shift-wise entries with no network, data is stored **encrypted on
device** (SQLCipher database + OS secure storage for the session), and entries
are securely synchronized when connectivity returns
(`POST /api/v1/sync/shift-entries`; the server re-validates every entry with
the same rules as online entry and returns per-entry accept/reject, which the
app shows against each queued row).

## Build (any machine with the Flutter SDK)

```bash
cd minetrace/field_app
flutter create . --platforms=windows,android   # scaffolds platform folders
flutter pub get
flutter run -d windows     # or: flutter run (pick the attached device)
```

## Default server URL

`http://10.0.2.2:19823/api/v1` (Android emulator -> host loopback). On desktop
or a real device, set it to the backend machine's LAN IP, e.g.
`http://192.168.x.x:19823/api/v1`. Log in with a foreman-bound account
(seed: any user whose role has `mine_id`, e.g. `r.kumar / demo123`).

## Offline demo flow (2 minutes)

1. Start the backend, launch the app, log in.
2. Turn on airplane mode (or stop the backend).
3. Add two shift entries - they queue with an orange "waiting" badge and are
   stored in the SQLCipher-encrypted local DB.
4. Turn airplane mode off and tap refresh - entries replay through the sync
   endpoint and flip to green SYNCED (server-validated IDs) or red REJECTED
   with the server's reason.

## Why local login (not Keycloak) in the field

A mine office cannot always reach the IdP. The web portal does SSO via
Keycloak (`/api/v1/auth/enterprise/*`); the field app authenticates against
the backend's local JWT so offline capture never depends on connectivity.
Sync-time revalidation is enforced server-side regardless.
