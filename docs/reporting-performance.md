# Reporting performance

Reporting uses owned request-scoped source lists and FX lookups. Measurements
must preserve financial results and record their workload and limits before
they support a change. The benchmark is a development tool, not a production
latency guarantee.

## Measurement method

Run from the repository root with the locked Python environment:

```bash
uv run python scripts/benchmark_reporting.py --samples 20 --output .local/test-results/reporting.json
```

The command owns a temporary database, environment file and signing key. Its
worker refuses an already configured Django installation and accepts no database
or server target. Each record count runs in a fresh process, seeds five years
of synthetic BRL spending and projects the ledger once. Up to twelve sources
recur monthly; roughly 10% of the remaining sources use six credit installments.

It measures warm synchronization and complete authenticated dashboard/report
GETs. The JSON includes median and p95 latency, SQL count, financial write count,
movement count and peak Python allocations, together with the source revision,
working-tree status and runtime environment. Keep raw output in ignored local
storage; it can contain host and working-tree metadata.

Timing excludes seeding, initial synchronization, SQL capture and memory
tracing. Memory is a separate warm call's Python heap peak, not process RSS.
These Django test-client measurements exclude HTTP transport, browser rendering,
cold caches and concurrent SQLite writers. Use the same revision scope, seed,
record counts and environment for before/after comparisons. Small differences
on a shared host do not establish a regression or improvement.

## Financial invariants

A faster report must retain amounts, currencies, dates, ownership, movement
counts and missing-evidence behavior. Check that warm read operations do not
write financial records. Do not add timing assertions to functional tests or
reduce validation gates to meet a benchmark target.

One owned request-local transaction list can serve related report chart islands.
Explicit shared sources must pass ownership checks and end with the request.
`banking.services.ConversionContext` also rejects reuse for another user; its
lookup cache cannot replace captured historical FX evidence. These are bounded
read optimizations, with no persisted reporting snapshot or global rate cache.

SQLite permits only one writer at a time. WAL and `IMMEDIATE` transactions do
not remove contention or establish concurrent-write capacity. Keep transactions
short and measure the actual workload before changing database/cache settings.
See [SQLite WAL](https://www.sqlite.org/wal.html) and
[Django SQLite transactions](https://docs.djangoproject.com/en/6.0/ref/databases/#transactions-behavior).
