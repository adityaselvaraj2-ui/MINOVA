import 'package:flutter/material.dart';

import 'api_client.dart';
import 'models.dart';
import 'offline_store.dart';
import 'sync_service.dart';

void main() => runApp(const MineTraceFieldApp());

class MineTraceFieldApp extends StatelessWidget {
  const MineTraceFieldApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MineTrace Field',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF1E3A5F), useMaterial3: true),
      home: const BootScreen(),
    );
  }
}

class BootScreen extends StatefulWidget {
  const BootScreen({super.key});

  @override
  State<BootScreen> createState() => _BootScreenState();
}

class _BootScreenState extends State<BootScreen> {
  OfflineStore? _store;
  String? _serverUrl;

  @override
  void initState() {
    super.initState();
    _open();
  }

  Future<void> _open() async {
    final store = await OfflineStore.open();
    final user = await store.loadSession();
    final server = await store.serverUrl();
    if (!mounted) return;
    setState(() {
      _store = store;
      _serverUrl = server;
    });
    if (user != null && server != null) {
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => HomeScreen(store: store, serverUrl: server, user: user),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_store == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return LoginScreen(store: _store!, serverUrl: _serverUrl);
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.store, this.serverUrl});

  final OfflineStore store;
  final String? serverUrl;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  late final TextEditingController _server;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _server = TextEditingController(
        text: widget.serverUrl ?? 'http://10.0.2.2:19823/api/v1');
  }

  Future<void> _login() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ApiClient(_server.text.trim());
      final user = await api.login(_username.text.trim(), _password.text);
      await widget.store.saveSession(user, _server.text.trim());
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => HomeScreen(store: widget.store, serverUrl: _server.text.trim(), user: user),
      ));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = 'Cannot reach server - check the URL');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MineTrace Field Login')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            TextField(controller: _server,
                decoration: const InputDecoration(labelText: 'Server URL')),
            TextField(controller: _username,
                decoration: const InputDecoration(labelText: 'Username')),
            TextField(controller: _password, obscureText: true,
                decoration: const InputDecoration(labelText: 'Password')),
            const SizedBox(height: 20),
            if (_error != null)
              Text(_error!, style: const TextStyle(color: Colors.red)),
            FilledButton(
              onPressed: _busy ? null : _login,
              child: Text(_busy ? 'Signing in...' : 'Sign in'),
            ),
          ],
        ),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen(
      {super.key, required this.store, required this.serverUrl, required this.user});

  final OfflineStore store;
  final String serverUrl;
  final FieldUser user;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final SyncService _sync;
  int _pending = 0;
  String? _syncMsg;
  List<QueuedEntry> _entries = [];

  @override
  void initState() {
    super.initState();
    _sync = SyncService(widget.store,
        ApiClient(widget.serverUrl)..token = widget.user.token);
    _refresh();
  }

  Future<void> _refresh() async {
    await _sync.syncNow();
    final pending = await widget.store.pendingCount();
    final entries = await widget.store.entries();
    if (!mounted) return;
    setState(() {
      _pending = pending;
      _entries = entries;
      _syncMsg = _sync.lastError;
    });
  }

  Future<void> _newEntry() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => NewEntryScreen(store: widget.store, mineId: widget.user.mineId),
    ));
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('MineTrace Field - ${widget.user.fullName}'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await widget.store.clearSession();
              if (!context.mounted) return;
              Navigator.of(context).pushReplacement(MaterialPageRoute(
                builder: (_) => const BootScreen(),
              ));
            },
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _newEntry,
        icon: const Icon(Icons.add),
        label: const Text('New shift entry'),
      ),
      body: Column(
        children: [
          ListTile(
            leading: Icon(_pending == 0 ? Icons.cloud_done : Icons.cloud_upload,
                color: _pending == 0 ? Colors.green : Colors.orange),
            title: Text(_pending == 0
                ? 'All entries synced'
                : '$_pending entries waiting to sync'),
            subtitle: Text(_syncMsg ?? 'Offline-first: entries are stored encrypted and replayed automatically'),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView.builder(
              itemCount: _entries.length,
              itemBuilder: (_, i) {
                final e = _entries[i];
                final color = switch (e.status) {
                  'SYNCED' => Colors.green,
                  'REJECTED' => Colors.red,
                  _ => Colors.orange,
                };
                return ListTile(
                  leading: Icon(Icons.description, color: color),
                  title: Text(
                      'Shift ${e.shiftLabel} - ${e.productionT} t, OB ${e.obM3} m3'),
                  subtitle: Text(
                      '${e.dateLabel} - ${e.status}${e.error == null ? '' : ': ${e.error}'}'),
                  trailing: e.status == 'REJECTED'
                      ? IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () async {
                            await widget.store.delete(e.localId!);
                            _refresh();
                          })
                      : null,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class NewEntryScreen extends StatefulWidget {
  const NewEntryScreen({super.key, required this.store, required this.mineId});

  final OfflineStore store;
  final int? mineId;

  @override
  State<NewEntryScreen> createState() => _NewEntryScreenState();
}

class _NewEntryScreenState extends State<NewEntryScreen> {
  final _bench = TextEditingController(text: '1');
  final _prod = TextEditingController();
  final _ob = TextEditingController();
  final _workers = TextEditingController(text: '12');
  DateTime _date = DateTime.now();
  String _shift = 'A';
  String? _error;

  Future<void> _save() async {
    final prodT = double.tryParse(_prod.text.trim());
    final obM3 = double.tryParse(_ob.text.trim());
    if (prodT == null || obM3 == null || widget.mineId == null) {
      setState(() => _error = 'Production (t), OB (m3) and a mine-bound login are required');
      return;
    }
    // Milli-units: the API contract stores integers (t*1000, m3*1000).
    final payload = <String, dynamic>{
      'mine_id': widget.mineId,
      'bench_id': int.tryParse(_bench.text.trim()) ?? 1,
      'work_date':
          '${_date.year}-${_date.month.toString().padLeft(2, '0')}-${_date.day.toString().padLeft(2, '0')}',
      'shift_code': _shift,
      'workers_present': int.tryParse(_workers.text.trim()) ?? 0,
      'production_milli_t': (prodT * 1000).round(),
      'ob_milli_m3': (obM3 * 1000).round(),
      'remarks': 'captured offline in field app',
    };
    await widget.store.queueEntry(payload);
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New shift entry (offline)')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(children: [
            Expanded(
              child: ListTile(
                title: const Text('Date'),
                subtitle: Text('${_date.year}-${_date.month}-${_date.day}'),
                trailing: const Icon(Icons.calendar_today),
                onTap: () async {
                  final d = await showDatePicker(
                    context: context,
                    initialDate: _date,
                    firstDate: DateTime(2024),
                    lastDate: DateTime.now().add(const Duration(days: 1)),
                  );
                  if (d != null) setState(() => _date = d);
                },
              ),
            ),
          ]),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            segments: ['A', 'B', 'C']
                .map((s) => ButtonSegment(value: s, label: Text('Shift $s')))
                .toList(),
            selected: {_shift},
            onSelectionChanged: (sel) => setState(() => _shift = sel.first),
          ),
          const SizedBox(height: 12),
          TextField(controller: _bench,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Bench ID')),
          TextField(controller: _prod,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Production (tonnes)')),
          TextField(controller: _ob,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Overburden (m3)')),
          TextField(controller: _workers,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Workers present')),
          const SizedBox(height: 16),
          if (_error != null)
            Text(_error!, style: const TextStyle(color: Colors.red)),
          FilledButton.icon(
            onPressed: _save,
            icon: const Icon(Icons.save),
            label: const Text('Queue encrypted & sync later'),
          ),
        ],
      ),
    );
  }
}
