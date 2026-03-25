## Context

The current project already models:

- company-to-company relationships in `data/company_relationships.csv`
- company-to-product relationships in `data/company_product_relationships.csv`
- product-to-product relationships in `data/product_relationships.csv`

The GUI can inspect these relationships, but there is no authoring surface for analysts to add new product-level upstream or downstream company links from inside the app. As a result, relationship enrichment must be done manually in CSV files and cannot easily support iterative chain curation.

This change adds an analyst workflow for maintaining product supply-chain mappings as first-class persisted data. The workflow needs to be simple enough for desktop use, but the stored output must still feed the same graph and impact logic used elsewhere in the project.

## Goals / Non-Goals

**Goals:**

- Let an analyst pick a company, then manage upstream and downstream companies for each of that company's products in a dedicated GUI page.
- Persist analyst-entered mappings so they survive application restarts.
- Reuse saved mappings when editing adjacent companies later, so the graph accumulates chain knowledge instead of treating each edit as isolated.
- Make saved mappings available to graph exploration and domino-effect analysis.

**Non-Goals:**

- Introducing authentication, approval flows, or concurrent edit handling.
- Migrating the project from CSV-backed storage to a database.
- Automatically inferring relationships from market data or text.
- Solving every relationship type beyond the product-level upstream/downstream company mapping described here.

## Decisions

### 1. Store analyst-managed mappings in a dedicated canonical dataset

Analyst-created product supply-chain mappings will live in a separate canonical CSV dataset rather than overwriting existing curated relationship files.

Suggested fields:

- `source_company`
- `source_product`
- `direction` with values such as `upstream` or `downstream`
- `related_company`
- `related_product` optional for later enrichment
- `relation`
- `weight`
- `rationale`
- `updated_at`

Rationale:

- Preserves a clear boundary between seed/reference data and analyst-authored extensions.
- Makes rollback and auditing easier.
- Avoids breaking existing loaders that assume current dataset semantics.

### 2. Merge the managed mappings into read models and propagation inputs

The editor dataset should not remain UI-only. Data-loading and insight services should merge the managed mappings with current relationship views so they appear in company exploration, network graphs, and later domino-effect analysis.

Rationale:

- The value of the editor is persistence plus reuse.
- Analysts expect later views and scenario runs to reflect what they saved.

### 3. Use chain-aware editing hints instead of automatic graph mutation beyond the saved row

When an analyst saves `Company A / Product X -> downstream -> Company B`, the system should make that relationship visible when later editing `Company B`, but it should not silently fabricate additional second-order relationships.

Rationale:

- Keeps stored facts explicit.
- Prevents accidental over-expansion of the graph based on implicit assumptions.
- Still delivers the desired domino-effect workflow because previously stored edges become visible and analyzable.

### 4. Add a dedicated management tab rather than overload the current explorer tab

The current company tab is optimized for inspection. The new authoring workflow needs editable forms, validation feedback, and a saved-relationship list.

Rationale:

- Avoids making the explorer tab harder to scan.
- Keeps inspection and authoring responsibilities clear.

## Risks / Trade-offs

- [Data consistency risk] Analysts may enter duplicate or conflicting relationships. -> Add validation for duplicate rows, self-links, unknown companies, and invalid weights.
- [Semantic risk] `upstream` and `downstream` may be interpreted differently across teams. -> Define direction semantics explicitly in the spec and UI copy.
- [Scope risk] Users may expect full recursive auto-population after a single save. -> Limit v1 to persistence, surfacing linked context, and reuse in later analysis.
- [Storage risk] CSV persistence is simple but not ideal for concurrent edits. -> Accept this for desktop v1 and keep the dataset append/replace rules explicit.

## Migration Plan

1. Add a canonical dataset schema for analyst-managed product supply-chain mappings.
2. Extend loaders and validation so the dataset can be read and written safely.
3. Add a new GUI management tab for editing and saving rows.
4. Merge saved rows into insight and graph read models.
5. Extend domino-effect analysis inputs so saved mappings participate in propagation context.

Rollback strategy:

- Hide the new GUI tab.
- Stop loading the managed mapping dataset.
- Leave the stored CSV file unused without disturbing existing canonical datasets.

## Open Questions

- Should the editor support creating a new product for a company if the product does not already exist in `company_product_relationships.csv`?
- Should saved mappings write through into `company_relationships.csv` and `product_relationships.csv`, or remain as a parallel dataset merged at read time?
- Does the domino-effect view need a dedicated visualization of analyst-entered chains in v1, or is reuse in existing graph/event views enough?
