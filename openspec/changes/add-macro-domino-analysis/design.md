## Context

The current platform models event propagation primarily from curated company-to-company, company-to-product, product-to-product, and product-to-market relationships. Scenario seeding is currently driven by event templates that match existing graph edges, which works for company-specific and supply-chain-specific shocks but not for top-down macroeconomic drivers.

Adding macro domino-effect analysis introduces a new seed source: macro factors and explicit exposure mappings. These exposures need to seed the same propagation engine without creating a separate simulation stack. The change therefore spans data modeling, scenario definition, seed resolution, and explainability.

## Goals / Non-Goals

**Goals:**
- Add canonical macro factor and macro exposure datasets that can be loaded alongside the current graph data.
- Support macro scenarios that seed impacts from factor exposures before reusing the existing propagation model.
- Keep macro-driven runs explainable by showing the macro factor, exposure link, and downstream propagation path.
- Preserve compatibility with the scenario engine direction described in `scenario-engine-contract`.

**Non-Goals:**
- Building a real-time macro data ingestion pipeline.
- Replacing the existing event-template system.
- Calibrating a predictive macro model or claiming statistical forecasting accuracy.
- Redesigning all propagation rules across the entire engine.

## Decisions

### 1. Model macro factors and macro exposures as separate canonical datasets

Macro factors and macro exposure mappings will be added as dedicated reference data rather than encoded indirectly in company relationship edges.

Rationale:
- Macro factors are not companies, products, or markets, so forcing them into current edge semantics would blur the graph model.
- A separate exposure layer makes it easier to curate, explain, and expand factor coverage over time.
- The resulting seed logic becomes explicit: factor -> exposure -> seeded entity.

Alternatives considered:
- Reuse existing `edges.csv`-style relations for macro factors.
  Rejected because it overloads the meaning of operational relationship edges and makes explanation noisier.
- Hardcode macro exposure logic inside scenario templates.
  Rejected because it duplicates exposure knowledge across templates and prevents reuse.

### 2. Reuse the existing propagation engine after macro seeding

Macro scenarios should generate initial impacted entities through exposure mappings, then hand those seed impacts to the existing propagation runtime.

Rationale:
- This keeps one traversal model for company, product, and market propagation.
- Existing layer, lag, decay, sign, and fundamental multiplier semantics remain intact.
- Macro support remains an extension of the engine, not a parallel engine.

Alternatives considered:
- Create a separate macro simulation engine.
  Rejected because it would duplicate propagation logic and fragment result semantics.

### 3. Extend scenario definitions rather than replace them

Macro scenarios should fit into the scenario engine contract as either:
- macro-aware templates in the scenario catalog, or
- inline scenario definitions with macro-factor seed configuration.

Rationale:
- This aligns macro analysis with the reusable scenario-engine direction already documented.
- Existing clients can continue to think in terms of “run a scenario,” not “choose an engine type.”

Alternatives considered:
- Introduce a separate top-level artifact for macro-only scenarios.
  Rejected because it increases surface area without clear benefit at this stage.

### 4. Preserve explainability with explicit macro seed traces

Macro-driven result rows and traces should include:
- the originating macro factor
- the direct exposure mapping used for seeding
- the retained downstream propagation path

Rationale:
- Analysts need to distinguish “why this was seeded” from “how it spread.”
- Current string-path explanation is not sufficient for top-down analysis where the initial driver matters as much as the downstream chain.

Alternatives considered:
- Reuse current generic path text only.
  Rejected because macro context would be partially lost and harder to inspect.

## Risks / Trade-offs

- [Exposure quality risk] Curated macro exposure data may be incomplete or subjective. → Start with a narrow semiconductor/electronics universe and require explicit rationales on exposure mappings.
- [Model semantics risk] Macro effects can behave differently from operational relationship effects. → Limit v1 to exposure-based seeding plus existing propagation rules, and document that calibration is curated rather than predictive.
- [Scope creep risk] Macro analysis can expand quickly into many factors, regions, and time-series models. → Keep the first release focused on a small set of reusable macro factors and curated scenarios.
- [Explainability risk] Analysts may confuse the macro seed step with later propagation steps. → Keep trace output structurally separated into seed source and downstream traversal.

## Migration Plan

1. Add canonical macro factor and macro exposure datasets plus validation rules.
2. Extend scenario definitions to support macro-factor-based seed resolution.
3. Update the seed-building layer to resolve macro exposures into initial impacted entities.
4. Extend result and trace payloads so macro-driven runs retain their source explanations.
5. Add an initial curated library of macro scenarios for the current coverage universe.
6. Update GUI and future engine clients to list and run macro scenarios through the same scenario execution path.

Rollback strategy:
- Remove macro scenario references from the catalog.
- Ignore macro exposure datasets during loading.
- Fall back to the existing company/event seeding behavior.

## Open Questions

- Should macro exposures point only to companies in v1, or also to products and markets from the start?
- Should macro factors be purely curated qualitative factors, or should the schema already anticipate numeric observed values and units?
- How should macro scenario severity interact with exposure weight when both are present?
- Should sector- and industry-level macro seeding be materialized as explicit entity mappings or derived dynamically from company metadata?
