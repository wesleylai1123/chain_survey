# Local Launch And Product Assumptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app easy to run locally and change the Product EPS Dashboard so analysts enter product Volume %, ASP %, and Gross Margin ppt assumptions.

**Architecture:** Reuse `core.product_earnings_engine.ProductScenario` and `simulate_product_scenario` as the single source of product-level scenario math. Keep the Tk dashboard as the orchestration layer that collects assumptions, renders deltas, and bridges them into company EPS through `core.company_earnings_bridge`.

**Tech Stack:** Python 3.11+, Tkinter, pandas, matplotlib, unittest, shell script, PowerShell.

---

### Task 1: Product Assumption Inputs In The Dashboard

**Files:**
- Modify: `app/product_eps_dashboard.py`
- Test: `tests/test_product_eps_dashboard_ui.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dashboard_uses_volume_asp_and_margin_inputs_to_calculate_eps(self) -> None:
    app = ProductEpsDashboard()
    app.withdraw()
    try:
        app.company_var.set("TestCo")
        app.period_var.set("2026Q2")
        app._build_product_inputs()
        app.scenario_rows["HBM"][0].set("10")
        app.scenario_rows["HBM"][1].set("20")
        app.scenario_rows["HBM"][2].set("5")

        app.calculate(quiet=True)

        self.assertEqual(app.metric_labels["scenario_eps"].cget("text"), "9.296")
        values = app.result_tree.item(app.result_tree.get_children()[0], "values")
        self.assertEqual(values[0], "HBM")
        self.assertEqual(values[1], "+32.00")
        self.assertEqual(values[2], "+19.40")
    finally:
        app.destroy()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_product_eps_dashboard_ui -v`
Expected: FAIL because the current dashboard stores only two inputs per product and treats them as revenue and gross-profit deltas.

- [ ] **Step 3: Implement dashboard changes**

Update `app/product_eps_dashboard.py` to:
- import `ProductScenario` and `simulate_product_scenario`
- store three `StringVar` values per product row
- label columns as `Volume Δ %`, `ASP Δ %`, and `Gross Margin Δ ppt`
- build impacts by calling `simulate_product_scenario(company, product, period, ProductScenario(...))`
- estimate product baseline revenue from company revenue and product mix/weight when `product_financials.csv` has no matching snapshot
- load demo values as percentages instead of direct currency deltas

- [ ] **Step 4: Run dashboard tests and full unit tests**

Run: `.venv/bin/python -m unittest tests.test_product_eps_dashboard_ui -v`
Expected: PASS.

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS.

### Task 2: Local One-Command Launch

**Files:**
- Create: `run.sh`
- Create: `run.ps1`
- Modify: `README.md`

- [ ] **Step 1: Add launcher tests**

Add tests that assert:
- `run.sh` exists and invokes `.venv/bin/python app/main.py`
- `run.ps1` exists and invokes `.venv\Scripts\python.exe app/main.py`
- README documents macOS/Linux and Windows quick start commands

- [ ] **Step 2: Run launcher tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_local_launchers -v`
Expected: FAIL because the launcher files do not exist yet.

- [ ] **Step 3: Create launchers and README quick start**

Create `run.sh` with:
- project-root detection
- venv creation when `.venv` is missing
- dependency install from `requirements.txt`
- GUI launch through `.venv/bin/python app/main.py`

Create `run.ps1` with equivalent PowerShell behavior using `.venv\Scripts\python.exe`.

Update README with one-command local quick start examples.

- [ ] **Step 4: Verify launchers and all tests**

Run: `.venv/bin/python -m unittest tests.test_local_launchers -v`
Expected: PASS.

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS.

### Task 3: UI Smoke Check

**Files:**
- Modify: `scripts/ui_smoke.py`
- Test: `tests/test_ui_smoke.py`

- [ ] **Step 1: Run the existing UI smoke flow**

Run: `UI_SMOKE_DEMO=1 .venv/bin/python scripts/ui_smoke.py`
Expected on a machine with screen capture support: `UI_SMOKE_OK` and a screenshot at `artifacts/product-eps-dashboard.png`.

- [ ] **Step 2: Keep screenshot capture cross-platform**

Use `scrot` when it exists for Linux CI, Pillow `ImageGrab` when the OS allows system screenshots, and dashboard figure export as a final local fallback.

- [ ] **Step 3: Commit the verified feature**

Run:

```bash
git add app/product_eps_dashboard.py tests/test_product_eps_dashboard_ui.py tests/test_local_launchers.py run.sh run.ps1 README.md docs/superpowers/plans/2026-09-05-local-launch-and-product-assumptions.md
git commit -m "feat: add local launchers and product assumptions UI"
```
