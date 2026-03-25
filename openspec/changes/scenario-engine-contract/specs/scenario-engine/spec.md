## ADDED Requirements

### Requirement: Scenario Request Contract

The scenario engine SHALL accept a structured `ScenarioRequest` as the canonical execution input for scenario runs.

The `ScenarioRequest` SHALL support:

- a scenario source of type `template` or `inline`
- an execution scope including `max_layers`
- a data context including explicit graph and fundamental snapshot references
- optional scenario overrides
- output options controlling trace and payload detail

#### Scenario: Run a template-backed scenario

- **GIVEN** a registered scenario template exists
- **WHEN** a client submits a `ScenarioRequest` with `scenario.source.type = template`
- **THEN** the engine uses that request as the canonical execution input
- **AND** the engine resolves the template before propagation begins

#### Scenario: Run an inline scenario

- **GIVEN** a client provides an inline scenario definition with seed rules
- **WHEN** a client submits a `ScenarioRequest` with `scenario.source.type = inline`
- **THEN** the engine uses the inline definition without requiring template registration


### Requirement: Scenario Result Contract

The scenario engine SHALL return a structured `ScenarioResult` as the canonical output of a scenario run.

The `ScenarioResult` SHALL include:

- a run identifier
- execution status
- resolved scenario metadata
- resolved data context metadata
- a summary section
- an impacts collection
- warnings and errors collections

#### Scenario: Successful scenario execution

- **GIVEN** a valid scenario request and resolvable input data
- **WHEN** the engine executes the scenario successfully
- **THEN** it returns a `ScenarioResult`
- **AND** the result contains `run_id`, `status`, `scenario_resolved`, `data_resolved`, `summary`, and `impacts`

#### Scenario: Execution with partial data coverage

- **GIVEN** a valid scenario request
- **AND** some impacted entities do not have fundamental enrichment coverage
- **WHEN** the engine completes execution
- **THEN** it returns a `ScenarioResult`
- **AND** the result includes a warning describing the partial coverage


### Requirement: Impact Rows Must Be Structured and Explainable

The scenario engine SHALL represent each retained impacted entity as a structured impact row in `ScenarioResult.impacts`.

Each impact row SHALL include:

- entity identity
- entity type
- direction
- absolute and signed impact values
- layer and cumulative lag
- dominant reason
- a reference to trace detail when trace output is enabled

#### Scenario: Company impact row is returned

- **GIVEN** a scenario run produces an impact on a company entity
- **WHEN** the engine returns the final result
- **THEN** the corresponding impact row includes entity identity, score fields, layer, lag, and dominant reason

#### Scenario: Trace reference is included when traces are requested

- **GIVEN** a scenario request enables trace output
- **WHEN** the engine returns an impact row for a retained impacted entity
- **THEN** the impact row includes a reference to a corresponding structured trace


### Requirement: Structured Trace Contract

The scenario engine SHALL provide a structured `ScenarioTrace` for explainable scenario outcomes.

The `ScenarioTrace` SHALL include:

- the final retained impact for the entity
- the originating seed information
- ordered propagation steps
- score adjustment details for each step
- a trace summary describing retained path information

#### Scenario: Explain why an entity was impacted

- **GIVEN** an impacted entity is present in a scenario result
- **WHEN** a client retrieves or inspects the entity trace
- **THEN** the trace identifies the seed rule and matched edge that initiated the impact
- **AND** the trace shows the propagation steps that reached the entity

#### Scenario: Show score adjustments in the trace

- **GIVEN** a propagation step applies relation, sector, industry, or fundamental adjustments
- **WHEN** the engine produces the structured trace
- **THEN** the step records the score before adjustments and the score after adjustments


### Requirement: Request Validation

The scenario engine SHALL validate `ScenarioRequest` inputs before execution.

The engine SHALL reject requests that:

- omit required scenario source fields
- define invalid `max_layers`
- define unsupported override fields or override values
- provide malformed inline seed rules
- reference explicit snapshots that cannot be resolved

#### Scenario: Reject a template request with no template identifier

- **GIVEN** a scenario request declares `scenario.source.type = template`
- **AND** `template_id` is missing
- **WHEN** the engine validates the request
- **THEN** the request is rejected with an error

#### Scenario: Reject a request with invalid layer depth

- **GIVEN** a scenario request defines `max_layers = 0`
- **WHEN** the engine validates the request
- **THEN** the request is rejected with an error because traversal depth must be at least `1`


### Requirement: Deterministic Run Metadata

The scenario engine SHALL include enough resolved metadata in `ScenarioResult` to support reproducibility for the same request and data context.

At minimum, the result SHALL record:

- engine version
- execution timestamp
- resolved scenario metadata
- resolved data context metadata

#### Scenario: Compare two runs of the same scenario

- **GIVEN** the same scenario request is executed multiple times
- **WHEN** a client compares the returned results
- **THEN** each result includes sufficient metadata to identify the engine version and resolved data context used for the run
