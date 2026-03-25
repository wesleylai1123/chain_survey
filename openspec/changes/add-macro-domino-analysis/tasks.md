## 1. Data Model and Canonical Datasets

- [x] 1.1 Add canonical macro factor dataset definitions, sample data files, and validation rules.
- [x] 1.2 Add canonical macro exposure mapping dataset definitions, sample data files, and validation rules.
- [x] 1.3 Extend data loading utilities to load macro factors and macro exposures alongside existing graph datasets.

## 2. Scenario Definition and Engine Seeding

- [x] 2.1 Extend scenario definitions to represent macro-factor-based scenarios and seed configuration.
- [x] 2.2 Implement seed resolution from macro exposures into initial impacted entities.
- [x] 2.3 Reuse the existing propagation runtime for macro-seeded runs without breaking current company-event scenarios.

## 3. Explainability and Client Surface

- [x] 3.1 Extend scenario result rows and traces to include macro factor and exposure-based explanations.
- [x] 3.2 Add an initial curated library of macro scenarios for the current semiconductor and electronics coverage universe.
- [x] 3.3 Update the desktop GUI and related read services to surface macro scenarios through the existing scenario execution flow.

## 4. Verification

- [x] 4.1 Add or update tests for macro dataset validation, macro seed resolution, and macro-driven propagation behavior.
- [x] 4.2 Validate the OpenSpec change and confirm the new macro scenarios can be loaded and executed through the defined flow.
