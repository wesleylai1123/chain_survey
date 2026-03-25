## Why

The current platform can simulate company- and supply-chain-centric events, but it does not model macroeconomic shocks such as FX moves, rate changes, commodity swings, or end-demand slowdowns as first-class domino-effect scenarios. This gap limits the usefulness of the engine for top-down analysis, which is often the starting point for analysts before they drill into company-level relationships.

## What Changes

- Add support for macroeconomic scenario definitions that can seed impacts into sectors, industries, markets, and exposed companies rather than only specific company-to-company events.
- Introduce a macro exposure layer so companies and products can be linked to macro factors such as exchange rates, rates, memory pricing, handset demand, AI capex, and regional demand.
- Extend the scenario engine output so macro-driven runs remain explainable, including the macro factor, exposure path, and downstream propagation rationale.
- Add a curated initial set of macro scenarios and macro exposure data focused on the existing semiconductor and electronics universe.

## Capabilities

### New Capabilities
- `macro-scenario-analysis`: Define, execute, and explain macroeconomic domino-effect scenarios across the business graph.
- `macro-exposure-modeling`: Represent macro factors and entity exposure links used to seed macro-driven propagation.

### Modified Capabilities

## Impact

- Affected engine logic in the scenario propagation layer, especially seeding and explanation.
- New canonical data files for macro factors, entity exposure mappings, and curated macro scenario templates.
- GUI and future API/notebook clients can reuse the same engine outputs once macro scenarios become first-class inputs.
