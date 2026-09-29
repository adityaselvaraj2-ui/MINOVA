# MineTrace Progress

## M0 Bootstrap - COMPLETE
- [x] Git init and environment checks
- [x] SETUP.md, README.md, ASSUMPTIONS.md, ARCHITECTURE.md
- [x] config.py with all settings
- [x] netguard.py — blocks non-loopback connections, Windows AF_UNIX fix
- [x] /health endpoint — reports DB, Ollama, netguard status
- [x] Tauri v2 + React + TypeScript + Tailwind frontend scaffolded
- [x] Health dashboard UI with status cards
- [x] Ruff lint clean, 4/4 pytest pass, tsc + vite build clean

## M1 Data Foundation - COMPLETE
- [x] Full SQLAlchemy schema — 17 tables matching spec §7.2
- [x] Alembic migration generated and applied
- [x] JWT auth with Argon2 hashing — POST /auth/login, GET /auth/me
- [x] RBAC with role-based access control
- [x] Masters APIs — subsidiaries, mines, benches, equipment, roles
- [x] Demo seed: 13,068 shift entries across 3 mines, 12 months, with downtime events
- [x] Full role hierarchy seeded (13 roles), approval chains, targets
- [x] Ruff clean, 10/10 pytest pass
