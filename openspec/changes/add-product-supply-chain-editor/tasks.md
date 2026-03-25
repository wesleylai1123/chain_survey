## 1. Data Model and Persistence

- [x] 1.1 Define a canonical dataset for analyst-managed product supply-chain mappings and add validation rules.
- [x] 1.2 Implement read/write utilities for the managed mapping dataset with duplicate and field validation.
- [x] 1.3 Decide and document how managed mappings are merged with existing relationship datasets at read time.

## 2. GUI Authoring Workflow

- [x] 2.1 Add a dedicated desktop GUI tab for selecting a company and product, then managing upstream/downstream companies.
- [x] 2.2 Add save, edit, delete, and validation feedback flows for managed mappings.
- [x] 2.3 Surface chain-aware context so previously saved adjacent mappings can be seen during later edits.

## 3. Analysis and Reuse

- [x] 3.1 Merge managed mappings into company insight and network graph views.
- [x] 3.2 Extend domino-effect analysis inputs so saved mappings can participate in downstream propagation context.
- [x] 3.3 Show enough relationship metadata in the GUI so analysts can tell which links are curated vs analyst-managed.

## 4. Verification

- [x] 4.1 Add or update tests for dataset validation, persistence, merge behavior, and duplicate handling.
- [x] 4.2 Verify the GUI can save a mapping, reload it after restart, and expose it in later company/impact views.
