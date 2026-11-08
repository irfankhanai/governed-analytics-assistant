# Five-minute hackathon demonstration

## Opening

“AI can amplify dashboard sprawl. This assistant checks the existing estate first and makes its evidence visible. Every record shown here is synthetic.”

1. Open **Overview**. Show the inventory, source rules, potential overlap and missing-owner validation findings.
2. Open **Analytics Request**, select **REQ-0001**, review the requirements table and check the confirmation box, then generate a recommendation. Show **HUMAN REVIEW**: the text asks for Nubeqa globally while structured fields say Beyonttra/EMEA. A clarification must be recorded; the app does not silently choose one. The summary states the next action, and approval is unavailable until the uncertainty is resolved.
3. Enter a new request: **Kerendia Commercial Reach Index Global**. Generate **BUILD NEW**. Show the ranked existing assets with zero KPI coverage, candidate semantic models and draft specification. Explain that this is an approved proposal workflow, not a generated Power BI report.
4. In **Approvals**, choose this decision, supply a demo identity, comments and owner-review attestation, then approve. Download the final report and show the stored source/configuration hashes. Restarting the app retains the approval.
5. In **Asset Explorer**, inspect **AST-0101**. Its metadata looks promising, but its SM-001 model declares another product and region. The assistant surfaces the contradiction rather than certifying reuse. Inspect retirement safeguards on a candidate-retire asset; low usage alone cannot authorize retirement.

## Reproducible controlled reuse

Run `python scripts/demo.py` using the project virtual environment. It verifies two original-data cases plus a controlled REUSE case. The controlled case changes SM-001's product to Beyonttra and region to EMEA **in memory only**, explicitly labeling this scenario in the report. It demonstrates how a consistent governed estate permits reuse; it is not a claim about the unmodified workbook. Reports and review history are in `runtime/demo/`.

The automated tests also derive controlled CONSOLIDATE, FIX and RETIRE cases from source records. They vary governance and dependency evidence to verify the outcome changes. The original workbook is never overwritten.

## Optional Power BI draft demonstration

Use **Kerendia Inventory Coverage Italy** to obtain a FIX proposal from the original workbook. After reviewing its evidence, record a demo approval with owner review and a remediation plan. Expand **Optional final step: Power BI project draft** in Approvals and prepare/download the ZIP. Show the source mappings before downloading. Extract the complete archive and open `Governed.pbip` in Power BI Desktop, then Refresh the embedded snapshot.

This export is a two-page table draft for the existing owner. It does not replace AST assets or publish anything. It is schema/reference checked but not yet Desktop-tested. Only show a live Desktop demo after separately confirming opening, refresh and rendering. The earlier Commercial Reach Index example intentionally cannot export: that KPI has no supported source-field mapping.

Alternatively, `python scripts/demo_pbip.py` writes an example ZIP and its approval to a separate database under `runtime/pbip-demo/`. No live approval records or source files are altered.

## Closing

“The result is a traceable decision, not another dashboard by default. Enterprise rollout would connect governed metadata and authenticated approval roles while retaining the same inspectable decision boundary.”
