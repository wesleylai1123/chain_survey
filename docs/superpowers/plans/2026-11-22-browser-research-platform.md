# Browser Research Platform Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans for the implementation.

**Goal:** Build one local browser workflow for arbitrary time-series comparison.

**Architecture:** Pandas-backed series preparation stays in `core/series_research.py`. The loopback server in `app/research_web.py` serves an HTML/Plotly frontend and calls the core for import and analysis.

**Tech Stack:** Python, pandas, scipy, Plotly, HTML and JavaScript.

- [x] In `tests/test_series_research.py`, verify cross-file import, actual calendar shifts, missing-period transforms, aggregation and availability. Confirm the tests fail before adding the core.
- [x] In `app/web_research/`, build the data library, chart, pair controls, results and chart-group actions. Exercise the import dialog and downloadable samples using a real browser.
- [x] In `app/research_web.py`, serve assets on loopback, validate incoming data and reuse the core. Set `app/main.py` to open the browser workspace by default. Retain the desktop workspace behind an explicit switch.
- [x] From a clean local server, load a CSV with its own dates, compare it with a built-in series, switch aggregation and lag, compare the displayed coefficients with an independent calculation, export and reload the chart group. Run the existing test suite and inspect desktop and narrow screenshots.
