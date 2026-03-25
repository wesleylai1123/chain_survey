# Scenario Engine Contract

## Goals

Define a reusable, explainable, client-independent contract for running scenario simulations over the existing business graph and fundamental signal model.

The contract should:

- decouple scenario execution from the desktop GUI
- preserve current event-template semantics where practical
- support reproducible runs through explicit data context
- support explainability through structured traces
- stay portable across GUI, notebook, batch, and future service clients

The contract should not yet:

- define network transport or API routes
- define persistence internals
- guarantee predictive accuracy
- solve multi-user or multi-tenant concerns

## Design Summary

The engine contract is centered on three objects:

- `ScenarioRequest`
- `ScenarioResult`
- `ScenarioTrace`

These correspond closely to the current codebase:

- scenario definitions are currently represented by event templates
- runtime execution is currently handled by `simulate_event()`
- score enrichment is currently handled by the fundamental signal layer
- path explanation is currently flattened into a string and should become structured

```text
ScenarioRequest
   |
   v
Scenario Engine
   |
   +--> ScenarioResult
   |
   +--> ScenarioTrace
```

## Request Schema

### Purpose

Describe what scenario to run, on what data context, with what execution scope, and with what overrides.

### Shape

```json
{
  "request_id": "string",
  "scenario": {
    "scenario_id": "string",
    "label": "string",
    "description": "string",
    "source": {
      "type": "template | inline",
      "template_id": "string",
      "definition": {}
    }
  },
  "scope": {
    "max_layers": 3,
    "as_of_date": "2026-03-25",
    "entity_filter": {
      "countries": ["Taiwan"],
      "sectors": ["Semiconductor"],
      "industries": ["IC Design"],
      "entity_types": ["company"]
    },
    "seed_filter": {
      "include_entities": ["台積電"],
      "exclude_entities": ["OPPO"]
    }
  },
  "overrides": {
    "severity": 1.0,
    "relation_rules": {
      "supplier_of": {
        "forward_decay": 0.88,
        "reverse_decay": 0.72,
        "forward_lag": 1,
        "reverse_lag": 1,
        "forward_sign": 1,
        "reverse_sign": 1
      }
    },
    "industry_sensitivity": {
      "IC Design": 1.15
    },
    "sector_sensitivity": {
      "Semiconductor": 1.1
    },
    "fundamental_mode": "enabled | disabled | neutral_only"
  },
  "data_context": {
    "graph_snapshot_id": "string",
    "fundamental_snapshot_id": "string",
    "event_catalog_version": "string"
  },
  "output_options": {
    "include_trace": true,
    "include_seed_rows": true,
    "include_non_company_nodes": false,
    "top_n_paths_per_impact": 3
  }
}
```

### Notes

- `scenario.source.type = template` preserves the existing event-template flow.
- `scenario.source.type = inline` enables ad hoc analyst scenarios without requiring template registration.
- `scope.as_of_date` should exist from the start even if early implementations map it to `latest`.
- `data_context` is required conceptually for reproducibility, even if initial snapshot resolution is coarse.
- `output_options` should allow compact outputs for batch use and richer outputs for interactive clients.

## Inline Scenario Definition

When `scenario.source.type = inline`, the `definition` payload should preserve the current event-template semantics:

```json
{
  "name": "string",
  "description": "string",
  "severity": 1.0,
  "max_layers": 3,
  "seed_rules": [
    {
      "match": {
        "relation": "supplier_of",
        "source": "台積電",
        "target": "聯發科"
      },
      "impact_on": "source | target",
      "sentiment": "positive | negative",
      "base_score": 0.95,
      "sensitivity": 1.0,
      "start_lag": 0,
      "allow_backflow": false,
      "reason": "string"
    }
  ],
  "industry_sensitivity": {
    "IC Design": 1.15
  },
  "sector_sensitivity": {
    "Semiconductor": 1.1
  },
  "relation_overrides": {
    "supplier_of": {
      "forward_decay": 0.88,
      "reverse_decay": 0.72,
      "forward_lag": 1,
      "reverse_lag": 1,
      "forward_sign": 1,
      "reverse_sign": 1
    }
  }
}
```

## Result Schema

### Purpose

Represent the canonical output of a scenario run, including execution metadata, resolved inputs, summary statistics, impacts, warnings, and errors.

### Shape

```json
{
  "request_id": "string",
  "run_id": "string",
  "status": "completed | failed | partial",
  "engine_version": "string",
  "executed_at": "2026-03-25T10:15:30Z",
  "scenario_resolved": {
    "scenario_id": "string",
    "name": "string",
    "description": "string",
    "severity": 1.0,
    "max_layers": 3
  },
  "data_resolved": {
    "graph_snapshot_id": "string",
    "fundamental_snapshot_id": "string",
    "event_catalog_version": "string"
  },
  "summary": {
    "seed_count": 1,
    "impacted_entity_count": 8,
    "impacted_company_count": 8,
    "positive_entity_count": 0,
    "negative_entity_count": 8,
    "max_layer_reached": 3,
    "top_positive_entity": null,
    "top_negative_entity": {
      "entity_id": "company:2454.TW",
      "entity_name": "聯發科",
      "impact_score": 0.98
    }
  },
  "impacts": [],
  "warnings": [],
  "errors": []
}
```

## Impact Row Schema

### Purpose

Represent one impacted entity in the resolved output set.

### Shape

```json
{
  "entity_id": "company:2454.TW",
  "entity_type": "company",
  "entity_name": "聯發科",
  "ticker": "2454.TW",
  "sector": "Semiconductor",
  "industry": "IC Design",
  "direction": "negative",
  "impact_score": 0.98,
  "signed_score": -0.98,
  "layer": 1,
  "cumulative_lag": 0,
  "fundamental_signal": -0.07,
  "fundamental_multiplier": 1.07,
  "dominant_reason": "先進製程成本上升，IC 設計客戶毛利承壓。",
  "trace_ref": "trace_0001"
}
```

### Notes

- `entity_id` should be stable and not rely on display names alone.
- `entity_type` future-proofs the engine for product and market impacts.
- `impact_score` is the absolute magnitude after propagation and multipliers.
- `signed_score` preserves directionality.
- `dominant_reason` is a summary explanation only, not a replacement for the full trace.

## Trace Schema

### Purpose

Provide structured explanation for how an impacted entity was reached and how its score was formed.

### Shape

```json
{
  "trace_id": "trace_0001",
  "run_id": "run_20260325_abc123",
  "entity_id": "company:2454.TW",
  "entity_name": "聯發科",
  "final_impact": {
    "direction": "negative",
    "impact_score": 0.98,
    "signed_score": -0.98,
    "layer": 1,
    "cumulative_lag": 0
  },
  "seed": {
    "seed_rule_index": 0,
    "matched_edge": {
      "source": "台積電",
      "source_type": "company",
      "relation": "supplier_of",
      "target": "聯發科",
      "target_type": "company",
      "weight": 0.95
    },
    "impact_on": "target",
    "sentiment": "negative",
    "base_score": 0.95,
    "severity": 1.0,
    "sensitivity": 1.0,
    "reason": "先進製程成本上升，IC 設計客戶毛利承壓。"
  },
  "steps": [
    {
      "step_index": 1,
      "from_entity": "台積電",
      "to_entity": "聯發科",
      "relation": "supplier_of",
      "direction": "forward",
      "edge_weight": 0.95,
      "decay": 1.0,
      "relation_sign": -1.0,
      "industry_multiplier": 1.15,
      "sector_multiplier": 1.1,
      "fundamental_multiplier": 1.07,
      "score_before_adjustments": -1.045,
      "score_after_adjustments": -0.98,
      "lag_added": 0
    }
  ],
  "trace_summary": {
    "dominant_path_rank": 1,
    "path_count_considered": 1,
    "path_count_retained": 1
  }
}
```

### Notes

- traces should preserve both causal structure and score arithmetic
- current string-based path output is insufficient for long-term engine reuse
- a result row should reference a trace via `trace_ref`
- trace retrieval can be separate from the main result payload for size control

## Validation

### Request Validation Errors

The engine should reject requests when:

- `scenario.source.type` is unsupported
- `template_id` is missing for template-backed scenarios
- `definition` is missing for inline scenarios
- `max_layers` is less than `1`
- `fundamental_mode` is invalid
- relation overrides use unsupported keys
- inline scenarios define no seed rules
- seed rules omit required fields
- `as_of_date` is malformed
- explicit snapshot identifiers cannot be resolved

### Execution-Time Errors

The request may be valid but execution may still fail when:

- the scenario template cannot be resolved
- graph data cannot be loaded
- fundamental data cannot be loaded when required
- entity metadata is inconsistent enough to prevent execution

### Warnings

The engine should return warnings rather than fail when:

- fundamental coverage is partial
- seed matches are sparse but non-zero
- entity filters exclude impacted entities from the output
- snapshot freshness does not align well with `as_of_date`
- unsupported entity types are ignored
- trace detail is truncated by output settings

### Error Rule

- use `error` when the run cannot produce a meaningful result
- use `warning` when the run completed with partial assumptions or partial coverage

## Determinism and Reproducibility

For the same request, resolved scenario, data snapshots, and engine version, the engine should aim to produce deterministic results.

At minimum, `ScenarioResult` should record:

- `engine_version`
- `scenario_resolved`
- `data_resolved`
- `executed_at`

This is the minimum needed to compare runs and explain drift.

## MVP Boundary

The minimum serious version of this contract should support:

- template-backed scenarios
- `max_layers`
- `as_of_date = latest`
- `fundamental_mode`
- company-level impact rows
- optional structured traces
- warnings for partial coverage

This is enough to decouple the engine boundary from the GUI without prematurely expanding into platform concerns.

## Open Questions

1. Should the engine optimize primarily for scenario sandboxing or decision support?
2. Should `entity_filter` constrain traversal or only final output?
3. Should the MVP return only company impacts or also product and market impacts?
4. How should multiple paths be aggregated when they reach the same entity?
5. What is the canonical long-term identity format for entities?
6. How should missing fundamentals be handled beyond neutral multipliers and warnings?
7. Should zero matched seeds be an error or a valid empty result?
8. How much of the fully resolved scenario should be echoed in the result payload?
9. Does `as_of_date` need real time-travel semantics in v1 or only explicit metadata?
10. Should traces expose only dominant paths or multiple retained paths?
