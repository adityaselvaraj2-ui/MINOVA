import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Thin client for the MineTrace FastAPI backend.
class ApiClient {
  ApiClient(this.serverUrl);

  /// e.g. http://10.0.2.2:19823/api/v1  (Android emulator -> host loopback)
  final String serverUrl;
  String? token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  /// POST /auth/login -> FieldUser (also used to re-validate cached sessions).
  Future<FieldUser> login(String username, String password) async {
    final resp = await http.post(
      Uri.parse('$serverUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );
    if (resp.statusCode != 200) {
      throw ApiException('Login failed (${resp.statusCode})');
    }
    final j = jsonDecode(resp.body) as Map<String, dynamic>;
    return FieldUser(
      token: j['access_token'] as String,
      username: j['username'] as String,
      roleCode: j['role_code'] as String,
      fullName: (j['full_name'] ?? '') as String,
      mineId: j['mine_id'] as int?,
    );
  }

  /// POST /sync/shift-entries - replay queued entries; server re-validates
  /// each one and returns per-entry accept/reject results.
  Future<SyncResult> syncEntries({
    required String deviceId,
    required List<Map<String, dynamic>> entries,
  }) async {
    final resp = await http.post(
      Uri.parse('$serverUrl/sync/shift-entries'),
      headers: _headers,
      body: jsonEncode({
        'device_id': deviceId,
        'captured_at': DateTime.now().toUtc().toIso8601String(),
        'entries': entries,
      }),
    );
    if (resp.statusCode == 401) {
      throw ApiException('Session expired - please log in again');
    }
    if (resp.statusCode != 200) {
      throw ApiException('Sync failed (${resp.statusCode})');
    }
    final j = jsonDecode(resp.body) as Map<String, dynamic>;
    final results = (j['results'] as List).cast<Map<String, dynamic>>();
    return SyncResult(
      accepted: (j['accepted'] ?? 0) as int,
      rejected: (j['rejected'] ?? 0) as int,
      results: results,
    );
  }

  /// GET /analytics/word-cloud style liveness probe (cheap, authed).
  Future<bool> reachable() async {
    try {
      final resp = await http
          .get(Uri.parse('$serverUrl/health'), headers: _headers)
          .timeout(const Duration(seconds: 4));
      return resp.statusCode < 500;
    } catch (_) {
      return false;
    }
  }
}

class SyncResult {
  SyncResult({
    required this.accepted,
    required this.rejected,
    required this.results,
  });

  final int accepted;
  final int rejected;
  final List<Map<String, dynamic>> results;
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}
