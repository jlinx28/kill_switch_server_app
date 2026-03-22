# Kill Switch Server

Remote device management server for the Dynamic POS app. Allows you to remotely block or unblock app access on registered devices via a web dashboard.

## How It Works

1. The POS app checks in with the server on every launch, sending its device ID and model
2. New devices are auto-registered and allowed by default
3. The admin dashboard lets you view all devices, tag them with owner names, and block/unblock access
4. Blocked devices see an "Access Revoked" screen and cannot use the app

## Folder Structure

### Server

```
kill_switch_server/
├── main.py              # FastAPI server (API + admin dashboard)
├── Dockerfile           # Container build spec
├── docker-compose.yml   # Deployment config
├── data/
│   └── devices.db       # SQLite database (auto-created, persisted via volume)
└── README.md
```

### Flutter App Client

```
lib/features/kill_switch/
├── data/
│   └── kill_switch_service.dart       # Server communication & device ID management
├── domain/
│   └── device_status.dart             # Response model
└── presentation/
    ├── providers/
    │   └── kill_switch_providers.dart  # Riverpod providers
    └── screens/
        ├── startup_screen.dart        # Launch verification screen
        └── blocked_screen.dart        # Access denied screen
```

## Tech Stack

- **Python 3.11** + **FastAPI** + **Uvicorn**
- **SQLite** for device storage
- **Docker** for deployment

## API Endpoints

| Method | Endpoint                            | Description                                                                |
| ------ | ----------------------------------- | -------------------------------------------------------------------------- |
| `GET`  | `/check/{device_id}?model=...`      | App check-in. Auto-registers new devices. Returns `{"access": true/false}` |
| `GET`  | `/{ADMIN_ROUTE}`                    | Admin dashboard (HTML)                                                     |
| `GET`  | `/{ADMIN_ROUTE}/toggle/{device_id}` | Toggle device block/unblock                                                |
| `POST` | `/{ADMIN_ROUTE}/tag/{device_id}`    | Set device tag/owner label                                                 |

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

- TODO: Replace <your-server-ip> with your actual VPS IP

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

| Variable      | Default              | Description                         |
| ------------- | -------------------- | ----------------------------------- |
| `DB_FILE`     | `devices.db`         | Path to SQLite database file        |
| `ADMIN_ROUTE` | `<YOUR_ADMIN_ROUTE>` | Obfuscated admin dashboard URL path |
| `TZ`          | `Asia/Manila`        | Timezone for timestamps             |

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

| File                                                                         | Purpose                                    |
| ---------------------------------------------------------------------------- | ------------------------------------------ |
| `lib/features/kill_switch/data/kill_switch_service.dart`                     | Server communication, device ID management |
| `lib/features/kill_switch/domain/device_status.dart`                         | Response model (`{"access": true/false}`)  |
| `lib/features/kill_switch/presentation/screens/startup_screen.dart`          | Launch check screen                        |
| `lib/features/kill_switch/presentation/screens/blocked_screen.dart`          | Access denied screen                       |
| `lib/features/kill_switch/presentation/providers/kill_switch_providers.dart` | Riverpod providers                         |

### Behavior

- **Fail-open**: If the server is unreachable (offline, timeout), the app allows access using the last cached status
- **Timeout**: 5 seconds — if the server doesn't respond, the app proceeds
- **Auto-register**: New devices are automatically registered on first launch with status `ACTIVE`
- **Persistent ID**: Device ID persists across app reinstalls via secure storage (except on emulators where secure storage may be unavailable)

## Code Snippets

> The admin dashboard HTML is generated inline in `main.py` — see the full file for the complete template.

### Flutter — `kill_switch_service.dart`

```dart
import 'dart:convert';
import 'dart:io';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';
import '../domain/device_status.dart';

class KillSwitchService {
   // TODO: Replace <YOUR_SERVER_IP> with your actual VPS IP
  static const _baseUrl = 'http://<YOUR_SERVER_IP>:8081';
  static const _timeout = Duration(seconds: 5);

  static const _keyDeviceId = 'kill_switch_device_id';
  static const _keyBlocked = 'kill_switch_blocked';

  final FlutterSecureStorage _storage;

  KillSwitchService({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  Future<String> getOrCreateDeviceId() async {
    try {
      var id = await _storage.read(key: _keyDeviceId);
      if (id == null) {
        id = const Uuid().v4();
        await _storage.write(key: _keyDeviceId, value: id);
      }
      return id;
    } catch (_) {
      return const Uuid().v4();
    }
  }

  Future<DeviceStatus> checkAccess() async {
    try {
      final deviceId = await getOrCreateDeviceId();
      final model = Uri.encodeComponent(_getDeviceModel());
      final uri = Uri.parse('$_baseUrl/check/$deviceId?model=$model');

      final response = await http.get(uri).timeout(_timeout);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final status = DeviceStatus.fromJson(data);
        try {
          await _storage.write(
            key: _keyBlocked,
            value: status.access ? 'false' : 'true',
          );
        } catch (_) {}
        return status;
      }

      return _fallback();
    } catch (_) {
      return _fallback();
    }
  }

  Future<DeviceStatus> _fallback() async {
    try {
      final blocked = await _storage.read(key: _keyBlocked);
      if (blocked == 'true') {
        return const DeviceStatus(access: false);
      }
    } catch (_) {}
    return const DeviceStatus(access: true);
  }

  String _getDeviceModel() {
    try {
      if (Platform.isAndroid) return 'Android Device';
      if (Platform.isIOS) return 'iOS Device';
      return 'Unknown';
    } catch (_) {
      return 'Unknown';
    }
  }
}
```

### Flutter — `device_status.dart`

```dart
class DeviceStatus {
  final bool access;

  const DeviceStatus({required this.access});

  factory DeviceStatus.fromJson(Map<String, dynamic> json) {
    return DeviceStatus(access: json['access'] as bool);
  }
}
```

### Flutter — `kill_switch_providers.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/kill_switch_service.dart';
import '../../domain/device_status.dart';

final killSwitchServiceProvider = Provider<KillSwitchService>(
  (_) => KillSwitchService(),
);

final deviceAccessProvider = FutureProvider<DeviceStatus>((ref) {
  return ref.read(killSwitchServiceProvider).checkAccess();
});
```

### Flutter — `startup_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/kill_switch_providers.dart';

class StartupScreen extends ConsumerWidget {
  const StartupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final accessAsync = ref.watch(deviceAccessProvider);

    return accessAsync.when(
      loading: () => const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.point_of_sale, size: 64, color: Colors.deepPurple),
              SizedBox(height: 24),
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('Verifying access...'),
            ],
          ),
        ),
      ),
      error: (_, __) {
        // Fail-open: allow access on unexpected errors
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (context.mounted) context.go('/');
        });
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      },
      data: (status) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (context.mounted) {
            context.go(status.access ? '/' : '/blocked');
          }
        });
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      },
    );
  }
}
```

### Flutter — `blocked_screen.dart`

```dart
import 'package:flutter/material.dart';

class BlockedScreen extends StatelessWidget {
  const BlockedScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.lock, size: 80, color: Colors.red.shade700),
                const SizedBox(height: 24),
                Text(
                  'Access Revoked',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Colors.red.shade700,
                      ),
                ),
                const SizedBox(height: 12),
                Text(
                  'This device has been blocked.\nPlease contact the administrator.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Colors.grey.shade600,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
```

## Local Development

```bash
pip install fastapi uvicorn python-multipart
uvicorn main:app --reload --port 8081
```

Dashboard: `http://localhost:8081/<YOUR_ADMIN_ROUTE>`

## Security Notes

- The admin dashboard URL is obfuscated (not `/admin`) but has **no authentication**. Restrict access via firewall rules or add auth if exposing to the public internet.
- The app uses a **fail-open** strategy: if the server is unreachable, the app defaults to allowing access (using cached status).
