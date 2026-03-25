## ADDED Requirements

### Requirement: Macro Scenarios Must Be First-Class Scenario Inputs

The platform SHALL support macroeconomic scenarios as first-class scenario definitions that can be executed by the scenario engine.

Macro scenarios SHALL support:

- a macro factor identifier
- a scenario direction such as positive or negative
- a scenario severity
- seed rules based on macro exposure rather than only company-to-company edges
- downstream propagation into exposed entities through the existing business graph

#### Scenario: Run a negative handset-demand macro scenario

- **GIVEN** a macro scenario is defined for weaker global handset demand
- **AND** the scenario includes seed rules tied to handset-demand exposure
- **WHEN** the analyst executes the scenario
- **THEN** the engine seeds impacts into directly exposed entities
- **AND** the engine propagates those impacts through the downstream relationship graph

#### Scenario: Run a positive AI capex macro scenario

- **GIVEN** a macro scenario is defined for stronger AI infrastructure spending
- **WHEN** the analyst executes the scenario
- **THEN** the engine can seed positive impacts into entities exposed to that macro factor
- **AND** the result preserves direction, score, layer, and lag semantics


### Requirement: Macro Scenarios Must Produce Explainable Results

The platform SHALL return explainable results for macro-driven scenario runs.

Macro scenario result rows SHALL include:

- the impacted entity
- the direction and magnitude of impact
- the dominant macro factor or rationale
- the propagation layer and lag
- a traceable explanation reference

#### Scenario: Explain the macro driver of a company impact

- **GIVEN** a company appears in the result of a macro-driven scenario
- **WHEN** the analyst inspects the result
- **THEN** the result identifies the macro factor that seeded the impact
- **AND** the result provides a trace or explanation reference for the retained path


### Requirement: Macro Scenarios Must Respect the Existing Propagation Model

The platform SHALL reuse the existing scenario propagation model for macro-driven runs after macro exposures have seeded the initial impacted entities.

#### Scenario: Macro exposure seeds into existing company graph propagation

- **GIVEN** a macro factor is linked to a company through an exposure mapping
- **WHEN** that company becomes a seeded impact in a macro scenario
- **THEN** subsequent propagation uses the standard relation-based traversal rules used by other scenario runs

