# Browser Research Platform

Chain Survey opens a local browser workspace for searching, charting and
correlating time series. Start with the repository's existing source-backed
monthly panel. CSV imports add numeric columns to the same searchable library
and preserve their dates, optional release timestamps, source and units.

Each series can use levels, differences, period returns or year-over-year
changes. Compare any two series on a daily, monthly or quarterly calendar
using an explicit last, mean or sum aggregation. Calendar gaps stay missing.
Historical availability is displayed when known. A strict mode requires
recorded dates for both series. Exploration can include unknown publication
dates, which are visibly identified.

The workspace shows interactive multi-series trends, a scatter plot, rolling
coefficients and lead/lag results. Analysis uses only aligned observations,
reports both Pearson and Spearman, and exports the exact samples and their
provenance. Users can keep named chart groups and imported series locally.

Launch through the existing app entry point and keep the desktop tools
available through their existing options. Serve on loopback only.
