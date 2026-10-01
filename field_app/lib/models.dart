/// MineTrace field data models (matched to the backend API contract).
class FieldUser {
  const FieldUser({
    required this.token,
    required this.username,
    required this.roleCode,
    required this.fullName,
    this.mineId,
  });

  final String token;
  final String username;
  final String roleCode;
  final String fullName;
  final int? mineId;

  Map<String, dynamic> toJson() => {
        'token': token,
        'username': username,
        'roleCode': roleCode,
        'fullName': fullName,
        'mineId': mineId,
      };

  static FieldUser fromJson(Map<String, dynamic> j) => FieldUser(
        token: j['token'] as String,
        username: j['username'] as String,
        roleCode: j['roleCode'] as String,
        fullName: (j['fullName'] ?? '') as String,
        mineId: j['mineId'] as int?,
      );
}

/// Local queue states: PENDING -> SYNCED (accepted) | REJECTED (server said no).
class QueuedEntry {
  QueuedEntry({
    this.localId,
    required this.payload,
    required this.status,
    this.serverId,
    this.error,
    this.createdAt,
  });

  final int? localId;
  final Map<String, dynamic> payload;
  final String status; // PENDING | SYNCED | REJECTED
  final int? serverId;
  final String? error;
  final DateTime? createdAt;

  String get shiftLabel =>
      (payload['shift_code'] ?? '?').toString().toUpperCase();
  String get dateLabel => (payload['work_date'] ?? '').toString();
  double get productionT =>
      ((payload['production_milli_t'] ?? 0) as int) / 1000;
  double get obM3 => ((payload['ob_milli_m3'] ?? 0) as int) / 1000;
}
