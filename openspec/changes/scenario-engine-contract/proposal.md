## Why

The current project contains the beginnings of a reusable scenario engine, but its execution contract is implicit and tightly coupled to the desktop GUI. Scenario execution currently centers on named event templates, in-memory CSV-backed graph state, and DataFrame outputs shaped for UI rendering.

This makes the engine difficult to reuse from other clients such as notebooks, batch jobs, or a future service layer. It also makes reproducibility and explainability weaker than they need to be for serious analyst workflows.

## What Changes

Define a client-independent scenario engine contract centered on three artifacts:

- `ScenarioRequest` for execution input
- `ScenarioResult` for canonical run output
- `ScenarioTrace` for structured explanation of how an impacted entity was reached

The contract will:

- make scenarios first-class execution inputs rather than GUI actions
- make data context explicit through snapshot-oriented fields
- preserve explainability via structured traces instead of path strings alone
- formalize validation, warning, and error semantics

## Non-Goals

- implementing a service API
- replacing the current desktop GUI
- solving multi-tenant platform concerns
- claiming predictive accuracy
- redesigning the current propagation model

## Expected Outcome

The project gains a stable engine boundary that can be used by multiple clients without depending on Tkinter-specific workflows. The GUI can remain as one client of the engine, while future notebook, batch, or API clients can reuse the same scenario contract and result schema.
