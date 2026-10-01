import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';
import 'offline_store.dart';

/// Replays the encrypted local queue against POST /sync/shift-entries
/// whenever connectivity returns. Server re-validates every entry with the
/// same rules as online entry and returns per-entry accept/reject, so the
/// client can mark each item SYNCED or REJECTED with the reason.
class SyncService {
  SyncService(this._store, this._api);

  final OfflineStore _store;
  final ApiClient _api;

  static const _deviceIdKey = 'mt_device_id';
  String? _lastError;
  DateTime? _lastSyncAt;
  bool _running = false;

  String? get lastError => _lastError;
  DateTime? get lastSyncAt => _lastSyncAt;

  Future<String> deviceId() async {
    const secure = FlutterSecureStorage();
    var id = await secure.read(key: _deviceIdKey);
    if (id == null || id.isEmpty) {
      id = 'fld-${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}';
      await secure.write(key: _deviceIdKey, value: id);
    }
    return id;
  }

  bool _isOnline(List<ConnectivityResult> results) =>
      results.any((r) => r != ConnectivityResult.none);

  /// One sync pass. Safe to call repeatedly; skips when offline or busy.
  Future<void> syncNow() async {
    if (_running) return;
    _running = true;
    try {
      final conn = await Connectivity().checkConnectivity();
      if (!_isOnline(conn)) {
        _lastError = 'offline';
        return;
      }
      final pending = await _store.pendingEntries();
      if (pending.isEmpty) {
        _lastError = null;
        return;
      }
      final results = await _api.syncEntries(
        deviceId: await deviceId(),
        entries: pending.map((e) => e.payload).toList(),
      );
      for (final r in results.results) {
        final local = pending[r['index'] as int];
        if (r['ok'] == true) {
          await _store.markSynced(local.localId!, r['id'] as int);
        } else {
          await _store.markRejected(local.localId!, (r['error'] ?? '') as String);
        }
      }
      _lastSyncAt = DateTime.now();
      _lastError = null;
    } on SocketException {
      _lastError = 'offline';
    } on ApiException catch (e) {
      _lastError = e.message;
    } catch (e) {
      _lastError = e.toString();
    } finally {
      _running = false;
    }
  }
}
