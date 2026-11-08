# Architecture and rule reference

## Boundaries

The source workbook is read-only. The loader attaches `_sheet` and `_row` to each record and calculates the file hash. Validation checks primary keys, composite asset/KPI and monthly-usage keys, foreign keys and lineage endpoints. Nullable owners are warnings, not automatically invalid assets. Broken keys and missing core catalogues block decisions.

The parser retains extracted entities, selected fields, contradictions and any explicit clarification. Matching is deterministic. Ties sort by score then original asset ID. The decision snapshot stores all ranked scope candidates with source evidence, rejected alternatives, configuration, original request and source hash.

SQLite stores immutable recommendation JSON in `decisions`, plus append-only review rows in `reviews`. A conditional status update within a transaction prevents double review. Connections enable foreign keys and close after use. Timestamps use UTC. A revised request creates a new decision; an old snapshot is never rewritten. `GOVERNED_ANALYTICS_DB` optionally selects another local database path.

## Workbook rules and implementation

| Source rule | Implementation | Outcome |
| --- | --- | --- |
| RULE-001 Reuse before build | Search all assets; rank endorsed assets; list product-compatible models | Endorsement warning is explicit; new build occurs only after coverage search |
| RULE-002 Canonical KPI first | Every mapped KPI must resolve and be approved/canonical | Unknown mapping → missing evidence; noncanonical/unapproved → remediation |
| RULE-003 Owner required | Asset owner must resolve and be active; model owner checked too | Missing → unknown; inactive → remediation |
| RULE-004 Lineage required | Require the declared model-to-asset edge; show all incident asset/model edges | Missing edge or contradictory model scope → human review |
| RULE-005 High reach requires trust | Audience ≥ 1,000 requires certified/promoted endorsement | Otherwise remediation; threshold is configurable |
| RULE-006 Do not migrate waste | Flag Tableau assets, show migration entries, detect overlap and retirement safeguards | Warning/context; migration candidate path is never executed |
| RULE-007 AI-ready semantics | Model readiness good and issue pattern clear | Other states → remediation; missing model → unknown |
| RULE-008 Explain every lifecycle action | Attach metadata, usage, KPI, lineage, quality and signal evidence to saved proposal | Evidence may be missing, but that absence is explicit |

Refresh status, lifecycle, quality issues, high severity signals, model owner and asset/model scope consistency are supplementary checks. They do not invent new source rule IDs. Signal observations need validation; they are not treated as authoritative ground truth. Asset/model scope mismatches are uncertainty, not proof that either record is correct.

## Important design tradeoffs

All mapped KPIs are checked for canonical status, even if a request uses only one. This deliberately conservative choice can require FIX for an otherwise useful asset. A missing owner on a zero-KPI-match asset does not prevent a new-build coverage finding, but an absent KPI map does. A scope-compatible partial match is offered for extension before separate content is proposed.

Approval is a proposal review, not implementation completion. High-risk lifecycle proposals require recorded attestations, but this demo cannot authenticate their truth. Retirement is intentionally separate from request fulfillment. It requires a suitable replacement; consolidation requires overlapping requested KPI coverage. Downstream checks include recorded direct dependencies; transitive completeness still needs human verification.

## Reproducibility

The Markdown report embeds the complete JSON snapshot and review history; JSON downloads preserve native structures. Formula, configuration and original record provenance remain inspectable after changes to the live source or configuration. Controlled fixtures mark their modified status in source metadata: their SHA identifies the original workbook, not a hash of the modified in-memory scenario.

## Security and deployment limits

No network API is used by the recommendation engine. SQL values are parameterized. The local Streamlit server binds to 127.0.0.1 and usage statistics are disabled. Do not deploy this prototype with confidential data or multiple users without identity, authorization, protected storage, audit controls and a reviewed threat model. No BI write connector exists.
