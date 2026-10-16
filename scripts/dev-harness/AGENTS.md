# Dev harness

Inherits [repository rules](../../AGENTS.md). The harness runs the local backend stack
(`make dev-up` / `dev-down`) and the memory scenarios in [MEMORY_SCENARIOS.md](MEMORY_SCENARIOS.md).

Run `bash scripts/dev-harness/run-tests.sh`. Tests use injected processes and clock and must
never contact production.
