# ABF primary-source acquisition playbook

This document defines where the ABF model should acquire missing operating data
before considering any secondary research source.

## Source order

1. TWSE/MOPS regulatory documents.
2. Company investor-conference presentations and videos.
3. Company annual/sustainability reports and product roadmaps.
4. Secondary research only for discovery. Secondary material must not enter
   `abf_operating_observations.csv`.

The machine-readable registry is `data/abf_source_registry.csv`.

## Extraction targets

### Utilization

Search investor material for utilization / capacity utilization / loading /
稼動率 / 滿載 / full utilization. Preserve ranges instead of coercing them into
an exact number.

Recommended representation:

- exact percentage: one numeric observation;
- percentage range: two observations or a future low/high schema;
- "full utilization": qualitative evidence, not an invented 100.0 value.

### Product mix

Prefer explicit ABF / BT / IC-substrate sales mix. A combined IC-substrate share
is only a proxy for ABF product mix and must retain its proxy relation.

### Capacity

Treat line starts, expansions, qualification, ramp-up and full-utilization dates
as supply events. These events are useful even when square-metre or panel
capacity is not disclosed.

### Volume proxy

When exact ABF shipment volume is unavailable, preserve production/output
metrics as a named proxy. Kinsus public sustainability data, for example,
contains annual production/output measures; these must never be relabelled
"ABF shipment volume" unless the source explicitly states that scope.

### Guidance and downside

Capture official management statements as point-in-time observations/events:
order visibility, demand recovery, price pressure, inventory correction,
customer delay, order cuts, yield issues, depreciation pressure, or weaker
utilization. Direction and scope must be explicit.

## Current official entry points

- Unimicron (3037): TWSE document archive is the guaranteed primary fallback.
- Kinsus (3189): official investor-conference archive plus sustainability
  reports and monthly revenue history.
- Nan Ya PCB (8046): official investor/financial archive and ABF technology
  roadmap.

## Acceptance rule

A discovered value is not calibration data until the row records:

- company / stock id;
- period or event date;
- metric scope;
- numeric value and unit where the source actually provides one;
- publication time/date;
- direct primary-source URL;
- source page or timestamp;
- short identifying excerpt.

Secondary sources may be stored separately as discovery leads, but must not
satisfy a coverage requirement.
