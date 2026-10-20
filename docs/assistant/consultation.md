# Owned consultations and monthly simulations

The assistant can consult the authenticated user's saved financial information
by default, independently of the visible workspace. The Context badge is
orientation, not an access boundary. There is no per-request page-data checkbox.
Provider authorization and inference remain separate, default-disabled gates.
The compatible `include_context` parameter only adds an initial-page snapshot;
it is not permission for the toolkit and does not limit reads to that page.

## Targeted evidence

`assistant.consultation.read_financial_data` accepts an allowlisted area, month,
name query, optional owned identifier and zero-based page. Areas cover accounts,
cards, invoices, transactions, categories, planning, goals, investments, reports,
exchange rates, loyalty and saved scenarios. Active owner/session authorization
is checked around every callback. Corrupt cross-owner relationships fail closed.

The initial request contains minimized page metadata, the current question and
up to nineteen completed history turns. Tools retrieve only the relevant saved
evidence; they do not copy the complete database. Responses retain capture date,
cutoff, currencies, missing-data warnings and verified local references. Lists
contain at most twenty rows with explicit pagination/truncation. An individually
selected record can supply necessary details; bulk lists omit private notes and
saved scenario payloads. Credentials, unsent forms, HTML and arbitrary SQL are
never available to the model.

Read tools reuse canonical services, never views or ledger synchronization.
Explicit conversion contexts avoid initializing preferences during reads.
Reports distinguish realized/forecast amounts; planning preserves reserves and
invoice obligations; investments preserve cost/market-value and missing-price/FX
semantics. Stored projections are not silently refreshed. References are retained
on the local run for replay and Markdown export.

## Monthly calculation

`assistant.simulation_tools.simulate_month` reuses `SalarySandboxForm`,
`sandbox.services.calculate_monthly_plan` and the read-only commitment snapshot.
The workspace keeps `_calculate_budget` as a compatibility alias. Inputs include
month, gross BRL salary, CLT payroll parameters and additional currency/percentage
expense rows. The implemented tax-rule year and source review date accompany the
result; no claim is made about a live external tax table for a different year.

Registered expenses use economic reference/statement month. Recurrences,
installments, split allocations and loyalty/IOF retain their ordinary meaning;
invoice payments are not counted as a second expense. Missing FX prevents an
invented final remainder. Results use Decimal-based numeric strings. Existing
record descriptions and private notes are not needed for aggregate simulation.

Other payroll deductions, an unrecorded extra expense and reducing a named
category are different hypotheses. Instructions ask for a short clarification
only when the distinction changes the result. Optional unspecified payroll
parameters default to zero; current month comes from the supplied cutoff.
`category_reductions` applies explicit hypothetical BRL cuts to an identified
category family using canonical monthly allocations. It reports baseline,
reduction and adjusted forecast, rejects overlapping families and cuts above
their forecast, and preserves missing-FX limits. It does not change saved limits,
cancel sources, refund settled spending or generate extra available bank cash.
Simulation creates no transaction, reservation, budget, preference or draft.
Persistent changes always use the separate [review and confirmation](actions.md).

## Provider and validation

The toolkit contains nine functions: one choice lookup, two read/calculation
tools and six preparation tools. At most five response requests and ten tool
calls share the existing 90-second budget. The ChatGPT adapter retains namespaced
function calling, `store: false`, streaming completion and bounded stateless
continuations. Unknown/malformed calls fail closed. There is no confirmation
tool, unrestricted execution, automatic retry, model substitution or paid API
fallback.

Version `v5` introduced these consultation rules. Current `v6` preserves them,
aligns citations with the verified reference footer and retains earlier
instruction files for explicit historical loading.
Offline tests establish deterministic contracts, calculations and no-write/
ownership boundaries, not a live model's tool selection or instruction compliance.
Current evidence belongs in dated reviews.
