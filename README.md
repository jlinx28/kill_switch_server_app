# Kill Switch Server

Remote device management server for the Dynamic POS app. Allows you to remotely block or unblock app access on registered devices via a web dashboard.

## How It Works

1. The POS app checks in with the server on every launch, sending its device ID and model
2. New devices are auto-registered and allowed by default
3. The admin dashboard lets you view all devices, tag them with owner names, and block/unblock access
4. Blocked devices see an "Access Revoked" screen and cannot use the app

## Tech Stack

- **Python 3.11** + **FastAPI** + **Uvicorn**
- **SQLite** for device storage
- **Docker** for deployment

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/check/{device_id}?model=...` | App check-in. Auto-registers new devices. Returns `{"access": true/false}` |
| `GET` | `/{ADMIN_ROUTE}` | Admin dashboard (HTML) |
| `GET` | `/{ADMIN_ROUTE}/toggle/{device_id}` | Toggle device block/unblock |
| `POST` | `/{ADMIN_ROUTE}/tag/{device_id}` | Set device tag/owner label |

## Database Schema

```sql
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    model TEXT,
    status INTEGER DEFAULT 1,    -- 1 = Active, 0 = Blocked
    last_seen TIMESTAMP,
    tag TEXT DEFAULT ''           -- Owner/device label
);
```

## Deployment

### Prerequisites

- Docker and Docker Compose installed on your server

### Deploy

```bash
scp -r kill_switch_server/ root@your-server-ip:/root/
ssh root@your-server-ip
cd /root/kill_switch_server
docker compose up -d --build
```

### Update

```bash
scp -r kill_switch_server/ root@your-server-ip:/root/
ssh root@your-server-ip
cd /root/kill_switch_server
docker compose up -d --build
```

The SQLite database is persisted in the `./data/` volume, so rebuilding the container won't lose device data.

## Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_FILE` | `devices.db` | Path to SQLite database file |
| `ADMIN_ROUTE` | `panel_x7k9m2` | Obfuscated admin dashboard URL path |
| `TZ` | `Asia/Manila` | Timezone for timestamps |

## Flutter App Integration

The kill switch client lives in the POS app at `lib/features/kill_switch/`.

### Setup

1. **Set the server URL** in `lib/features/kill_switch/data/kill_switch_service.dart`:

```dart
static const _baseUrl = 'http://<YOUR_SERVER_IP>:8081';
```

2. **Required dependencies** in `pubspec.yaml`:

```yaml
dependencies:
  http: ^1.2.0
  flutter_secure_storage: ^9.2.4
  uuid: ^4.5.1
```

### How It Works in the App

- On launch, the app navigates to `/startup` (configured in `lib/app/router.dart`)
- `StartupScreen` calls `KillSwitchService.checkAccess()` which sends a `GET /check/{device_id}?model=...` request
- If access is granted → navigates to the main app (`/`)
- If access is blocked → navigates to `/blocked` (shows "Access Revoked" screen)
- Device ID is a UUID v4, generated once and stored in `FlutterSecureStorage`

### Key Files

| File | Purpose |
|------|---------|
| `lib/features/kill_switch/data/kill_switch_service.dart` | Server communication, device ID management |
| `lib/features/kill_switch/domain/device_status.dart` | Response model (`{"access": true/false}`) |
| `lib/features/kill_switch/presentation/screens/startup_screen.dart` | Launch check screen |
| `lib/features/kill_switch/presentation/screens/blocked_screen.dart` | Access denied screen |
| `lib/features/kill_switch/presentation/providers/kill_switch_providers.dart` | Riverpod providers |

### Behavior

- **Fail-open**: If the server is unreachable (offline, timeout), the app allows access using the last cached status
- **Timeout**: 5 seconds — if the server doesn't respond, the app proceeds
- **Auto-register**: New devices are automatically registered on first launch with status `ACTIVE`
- **Persistent ID**: Device ID persists across app reinstalls via secure storage (except on emulators where secure storage may be unavailable)

## Local Development

```bash
pip install fastapi uvicorn python-multipart
uvicorn main:app --reload --port 8081
```

Dashboard: `http://localhost:8081/panel_x7k9m2`

## Security Notes

- The admin dashboard URL is obfuscated (not `/admin`) but has **no authentication**. Restrict access via firewall rules or add auth if exposing to the public internet.
- The app uses a **fail-open** strategy: if the server is unreachable, the app defaults to allowing access (using cached status).
