## Why

The current desktop GUI can display company-level upstream/downstream links and product dependency views, but it does not provide a dedicated workflow for analysts to curate product-level supplier and customer companies for a specific company. Relationship data is currently CSV-backed and largely static, which makes it difficult to iteratively enrich the graph from analyst knowledge.

This is a gap for domino-effect analysis. If an analyst knows that a company's specific product line depends on or sells into particular companies, that mapping should be captured once, stored persistently, and then reused when later configuring adjacent upstream or downstream companies. Without this workflow, relationship curation remains fragmented and the impact graph cannot accumulate analyst-entered knowledge over time.

## What Changes

- Add a new desktop GUI page for editing a selected company's product-level upstream and downstream company mappings.
- Introduce persistent storage for analyst-managed product supply-chain mappings, including the source company, source product, related company, direction, weight, and rationale.
- Extend the data-loading and graph-building flow so saved mappings become reusable relationship inputs for later configuration and domino-effect analysis.
- Show chain-aware context in the editor so previously saved mappings can inform later edits and make potential follow-on impact paths visible.

## Non-Goals

- Building a collaborative multi-user workflow or conflict resolution system.
- Replacing the existing curated canonical datasets with a database-backed authoring platform.
- Claiming predictive accuracy for the resulting domino-effect analysis.
- Redesigning the full scenario engine or all GUI tabs.

## Capabilities

### New Capabilities

- `product-supply-chain-management`: Create, persist, inspect, and reuse company-product upstream/downstream company mappings in the GUI.

## Impact

- Affected GUI surface in the Tkinter desktop app through a new relationship management page.
- New or extended canonical data file(s) to store analyst-managed product supply-chain mappings.
- Loader, insight, and graph/impact services will need to merge saved mappings with existing relationship datasets.
- Future configuration sessions can build on previously saved mappings, enabling visible domino-style chain accumulation across companies.
