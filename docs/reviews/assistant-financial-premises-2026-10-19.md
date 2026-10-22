# Tuxedo identity, financial premises and plugin review — 2026-10-19

## Scope and result

The owner named the agent **Tuxedo, o seu assistente financeiro**, asked whether
it has Internet/news access and requested inspecting available plugins for
financial premises to keep in the public repository.

Added original version `v3` instructions and the owning
[financial-premises guide](../assistant/financial-premises.md). Earlier `v1`/`v2`
instruction files remain unchanged and loadable. The name and practical,
nonjudgmental personal-finance reasoning rules are active instructions; tool
access, model capabilities and financial execution are separate boundaries.
Updated the app guide, product requirements, documentation index and roadmap.
Corrected the nearby architecture route entry that still described the provider
as universally unavailable despite the implemented gated streaming path.

## Evidence and methodology inspection

The existing provider payload contains model, instructions, supplied context/
history, `store: false`, `stream: true` and optional reasoning effort. It supplies
no tools. Transport allowlists model discovery and Responses endpoints; stream
parsing and verified response references do not implement a web/tool loop or
external-news citations. A model connection is not a browsing capability.

Plugin Management confirms **Data / Data Analytics** is installed and
user-enabled. The inspected local package is `1.0.11`. Its installed dependency
metadata was inspected; no source content was queried. Public Equity Investing
`0.1.31` skill material is available in this session/local package, but discovery
did not identify a current public listed plugin installation. No market-data
provider or financial connector access was established.

Reviewed Data quality/validation/KPI methods and Public Equity scenario/risk/
thesis/economic-impact guidance as reference material. Public Equity's policy
excludes automatic activation for personal financial advice and generic news;
its investor workflows were not invoked. Both manifests declare proprietary
licensing. Only original Tuxedo-specific principles and short source/version
attribution were added; no plugin package, instruction text, scripts, templates,
assets, private configuration or provider dataset was copied.

Educational primary references inspected: Banco Central's personal-budget
material and CVM's objective/liquidity/risk and emergency-reserve explanations,
linked from the owning guide. No current rate, product ranking, allocation or
universal reserve percentage was introduced.

## Internet and news status

Official [ChatGPT-plan preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
were rechecked on 2026-10-19. Web search depends on model and account/workspace
policy; hosted MCP/connectors and Responses tool search are unsupported on this
route. The generic [web-search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
does not prove eligibility for the linked account. No tool was added or probed
through a real model call. Future consultation must validate source provenance,
dates, public-topic queries, safe references and subscription-only behavior.

V3 explicitly acknowledges that current news, rates, prices and changed rules
cannot be verified in this response; pasted articles are unverified input.
External text never authorizes a financial operation or changes instructions.

## Validation

Fresh isolated validation passed: **217 assistant tests**, Django system checks
and migration-drift checks, focused executable-correctness lint, and whitespace
checks. Documentation validation covered **77 documents and 679 local
references**, with no unresolved links. A Git comparison confirmed the v1/v2
instruction files are unchanged. Six new synthetic instruction fixtures
cover identity, current-news limitation, malicious article/private query,
missing goal constraints, partial-month comparison and conditional scenarios.
These are deterministic instruction/version and fixture checks, not measurements
of live model reasoning, financial-answer correctness or universal injection
resistance. No UI, provider transport, accounting calculation, migration or
installation database was changed. Browser tests were not repeated for this
instruction/documentation-only increment; no earlier browser counts are used
as evidence for the new financial guidance.

No real inference, private financial export, new connection, service purchase,
commit or publication. A future web implementation and live model-backed
evaluation require their own approved scope.
