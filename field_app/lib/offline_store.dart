import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:sqflite_sqlcipher/sqflite.dart';
import 'package:path/path.dart' as p;

import 'models.dart';

/// Encrypted local store: the shift-entry queue lives in a SQLCipher-
/// encrypted database (key held in the device secure storage), and the JWT
/// lives in the OS secure storage. Nothing sensitive is plaintext on disk.
class OfflineStore {
  OfflineStore._(this._db, this._secure);

  static const _dbKey = 'mt_db_key';
  static const _tokenKey = 'mt_token';
  static const _userKey = 'mt_user';
  static const _serverKey = 'mt_server_url';

  final Database _db;
  final FlutterSecureStorage _secure;

  static Future<OfflineStore> open() async {
    const secure = FlutterSecureStorage(
      aOptions: AndroidOptions(encryptedSharedPreferences: true),
    );
    var dbKey = await secure.read(key: _dbKey);
    if (dbKey == null || dbKey.isEmpty) {
      dbKey = DateTime.now().microsecondsSinceEpoch.toRadixString(36) +
          _randSuffix();
      await secure.write(key: _dbKey, value: dbKey);
    }
    final docsDir = await getDatabasesPath();
    final db = await openDatabase(
      p.join(docsDir, 'minetrace_field.db'),
      password: dbKey,
      version: 1,
      onCreate: (d, v) async {
        await d.execute('''
          CREATE TABLE queued_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            server_id INTEGER,
            error TEXT,
            created_at TEXT NOT NULL
          )
        ''');
      },
    );
    return OfflineStore._(db, secure);
  }

  static String _randSuffix() {
    final r = DateTime.now().microsecondsSinceEpoch;
    return (r * 7919).toRadixString(36);
  }

  // ---- session ----
  Future<void> saveSession(FieldUser user, String serverUrl) async {
    await _secure.write(key: _tokenKey, value: user.token);
    await _secure.write(key: _userKey, value: jsonEncode(user.toJson()));
    await _secure.write(key: _serverKey, value: serverUrl);
  }

  Future<FieldUser?> loadSession() async {
    final raw = await _secure.read(key: _userKey);
    if (raw == null) return null;
    try {
      return FieldUser.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<String?> serverUrl() => _secure.read(key: _serverKey);

  Future<void> clearSession() async {
    await _secure.delete(key: _tokenKey);
    await _secure.delete(key: _userKey);
  }

  // ---- queue ----
  Future<int> queueEntry(Map<String, dynamic> payload) async {
    return _db.insert('queued_entries', {
      'payload': jsonEncode(payload),
      'status': 'PENDING',
      'created_at': DateTime.now().toUtc().toIso8601String(),
    });
  }

  Future<List<QueuedEntry>> entries() async {
    final rows = await _db.query(
      'queued_entries',
      orderBy: 'id DESC',
      limit: 200,
    );
    return rows.map(_fromRow).toList();
  }

  Future<int> pendingCount() async {
    final n = await _db.rawQuery(
      "SELECT COUNT(*) AS n FROM queued_entries WHERE status = 'PENDING'",
    );
    return (n.first['n'] as int?) ?? 0;
  }

  Future<List<QueuedEntry>> pendingEntries() async {
    final rows = await _db.query(
      'queued_entries',
      where: "status = 'PENDING'",
      orderBy: 'id ASC',
      limit: 100,
    );
    return rows.map(_fromRow).toList();
  }

  Future<void> markSynced(int localId, int serverId) =>
      _updateStatus(localId, 'SYNCED', serverId: serverId);

  Future<void> markRejected(int localId, String error) =>
      _updateStatus(localId, 'REJECTED', error: error);

  Future<void> requeue(int localId) =>
      _updateStatus(localId, 'PENDING');

  Future<void> delete(int localId) =>
      _db.delete('queued_entries', where: 'id = ?', whereArgs: [localId]);

  Future<void> _updateStatus(int localId, String status,
      {int? serverId, String? error}) async {
    await _db.update(
      'queued_entries',
      {
        'status': status,
        if (serverId != null) 'server_id': serverId,
        if (error != null) 'error': error,
      },
      where: 'id = ?',
      whereArgs: [localId],
    );
  }

  QueuedEntry _fromRow(Map<String, Object?> row) => QueuedEntry(
        localId: row['id'] as int,
        payload:
            jsonDecode(row['payload'] as String) as Map<String, dynamic>,
        status: (row['status'] ?? 'PENDING') as String,
        serverId: row['server_id'] as int?,
        error: row['error'] as String?,
        createdAt: row['created_at'] == null
            ? null
            : DateTime.tryParse(row['created_at'] as String),
      );

  Future<void> close() => _db.close();
}
