## ADDED Requirements

### Requirement: Macro Factors Must Be Modeled as Canonical Reference Data

The platform SHALL define canonical macro factor records that can be reused across scenarios and exposure mappings.

Macro factor records SHALL support:

- a stable factor identifier
- a display name
- a category
- a unit or qualitative scale
- a description

#### Scenario: Reference a macro factor from a scenario

- **GIVEN** a macro factor exists in canonical reference data
- **WHEN** a macro scenario refers to that factor
- **THEN** the factor can be resolved consistently across scenario definitions and exposures


### Requirement: Entities Must Support Macro Exposure Mappings

The platform SHALL support explicit mappings between macro factors and exposed entities.

Exposure mappings SHALL support:

- the factor being referenced
- the exposed entity
- exposure direction
- exposure strength or weight
- an explanation or rationale

#### Scenario: Map a company to FX exposure

- **GIVEN** a company has meaningful exposure to FX movements
- **WHEN** the macro exposure dataset is loaded
- **THEN** the company can be resolved as exposed to the referenced FX factor
- **AND** the exposure includes a direction and weight

#### Scenario: Map a product or market to end-demand exposure

- **GIVEN** a product or market is sensitive to a macro demand factor
- **WHEN** the macro exposure dataset is loaded
- **THEN** the product or market can be resolved as exposed to that factor


### Requirement: Macro Exposure Data Must Support Scenario Seeding

The platform SHALL use macro exposure mappings as a valid source of scenario seeding for macro-driven runs.

#### Scenario: Seed impacted entities from macro exposures

- **GIVEN** a macro scenario references a macro factor
- **AND** exposure mappings exist for that factor
- **WHEN** the engine resolves seed candidates for the scenario
- **THEN** directly exposed entities become eligible seed impacts for propagation

