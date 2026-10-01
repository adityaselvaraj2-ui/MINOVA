import 'package:flutter_test/flutter_test.dart';

import 'package:minetrace_field/models.dart';

void main() {
  test('QueuedEntry milli-unit getters convert to display units', () {
    final entry = QueuedEntry(
      payload: {
        'shift_code': 'a',
        'work_date': '2026-10-01',
        'production_milli_t': 29167,
        'ob_milli_m3': 34417500,
      },
      status: 'PENDING',
    );

    expect(entry.shiftLabel, 'A');
    expect(entry.dateLabel, '2026-10-01');
    expect(entry.productionT, 29.167);
    expect(entry.obM3, closeTo(34417.5, 0.001));
  });

  test('QueuedEntry handles missing milli-unit fields', () {
    final entry = QueuedEntry(
      payload: {'shift_code': 'B'},
      status: 'PENDING',
    );

    expect(entry.productionT, 0.0);
    expect(entry.obM3, 0.0);
  });
}
