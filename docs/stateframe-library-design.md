# stateframe Library Design Notes

This document starts turning the EDA capability map into a simple Python library.
The problem is not that data scientists lack statistics. The problem is that
many powerful diagnostics are scattered across libraries, require different
input shapes, produce incompatible outputs, and rarely explain what to do next.

`stateframe` should feel like a small library with a large brain.

## Core Promise

```python
import stateframe as sf

profile = sf.profile("data/sales/*.parquet")
profile.summary()
profile.issues()
profile.plot("concentration", column="revenue")
profile.report("sales-report.html")
```

The simple surface:

- `sf.profile(data)`
- `sf.compare(left, right)`
- `sf.scan(data)`
- `sf.plot(data_or_profile, kind, ...)`
- `sf.suggest(data_or_profile, what="checks")`
- `sf.report(data_or_profile, path)`

Everything else should be discoverable through these entry points.

## Design Goals

- One obvious way to start.
- Works in notebooks, scripts, and terminals.
- Returns useful Python objects, not just rendered reports.
- Supports DataFrames and Parquet paths with the same mental model.
- Lets users choose fast/approximate/deep scans.
- Lets advanced users call individual diagnostics directly.
- Keeps the default output concise.
- Makes every metric traceable.
- Makes reports reproducible.
- Does not force plotting dependencies unless needed.

## Package Shape

Potential source tree:

```text
src/
  stateframe/
    __init__.py
    api.py
    profile.py
    compare.py
    config.py
    datasets.py
    types.py
    issues.py
    metrics/
      __init__.py
      numeric.py
      categorical.py
      datetime.py
      text.py
      missingness.py
      relationships.py
      concentration.py
      parquet.py
      drift.py
    plots/
      __init__.py
      specs.py
      renderers.py
      numeric.py
      categorical.py
      missingness.py
      concentration.py
      relationships.py
    backends/
      __init__.py
      pandas.py
      polars.py
      arrow.py
      duckdb.py
      parquet.py
    reports/
      __init__.py
      html.py
      markdown.py
      json.py
    contracts/
      __init__.py
      pandera.py
      great_expectations.py
      yaml.py
    cli.py
```

## Dependency Strategy

Core install should stay light:

```text
stateframe
  pandas
  pyarrow
  numpy
  scipy
  rich
```

Optional extras:

```text
stateframe[plots]        # matplotlib, seaborn
stateframe[viz]          # plotly, altair
stateframe[polars]       # polars
stateframe[duckdb]       # duckdb
stateframe[contracts]    # pandera, great-expectations
stateframe[ml]           # scikit-learn, statsmodels
stateframe[text]         # optional NLP helpers
stateframe[all]
```

The base package includes the notebook widget experience. It should not require
every plotting, ML, or validation library for a simple profile.

## Main Concepts

### DatasetRef

A normalized reference to input data.

It can represent:

- pandas DataFrame.
- Polars DataFrame or LazyFrame.
- PyArrow Table or Dataset.
- DuckDB relation.
- Parquet file.
- Parquet directory.
- Glob.
- CSV later.

It stores:

- Original input.
- Resolved files.
- Backend choice.
- Whether data is lazy.
- Estimated rows and bytes.
- Scan capabilities.

### Profile

The main EDA result object.

It contains:

- Dataset summary.
- Column profiles.
- Relationship summaries.
- Missingness summaries.
- Storage metadata.
- Issue list.
- Plot registry.
- Method metadata.
- Sample metadata.
- Runtime metadata.

Methods:

```python
profile.summary()
profile.columns()
profile.column("revenue")
profile.issues(severity="warning")
profile.metrics()
profile.plots()
profile.plot("histogram", column="revenue")
profile.compare(other_profile)
profile.to_dict()
profile.to_json("profile.json")
profile.to_markdown("profile.md")
profile.to_html("profile.html")
profile.suggest("checks")
profile.suggest("features")
```

### ColumnProfile

Represents one column.

Methods:

```python
col = profile.column("revenue")

col.summary()
col.metrics()
col.issues()
col.plot("distribution")
col.plot("qq")
col.plot("concentration")
col.suggest("transformations")
```

### Issue

A finding that should get the user's attention.

Fields:

- `id`
- `title`
- `severity`
- `confidence`
- `columns`
- `description`
- `why_it_matters`
- `suggested_action`
- `method`
- `exact`
- `sampled`

Example:

```python
Issue(
    id="numeric.heavy_tail",
    title="Revenue has a heavy right tail",
    severity="info",
    confidence=0.91,
    columns=["revenue"],
    why_it_matters="Means and standard deviations may be unstable.",
    suggested_action="Inspect the Lorenz curve and consider log1p transforms.",
)
```

### PlotSpec

Plots should be represented before they are rendered.

Fields:

- `kind`
- `title`
- `data`
- `mark`
- `encoding`
- `transforms`
- `method_notes`
- `renderer_options`

This lets the same diagnostic become:

- Notebook output.
- Matplotlib figure.
- Plotly figure.
- Altair chart.
- HTML report section.
- Saved PNG/SVG.

## User-Facing API

### `profile`

Primary entry point.

```python
profile = sf.profile(data)
```

Useful options:

```python
profile = sf.profile(
    data,
    mode="standard",          # quick, standard, deep
    sample=None,              # None, int, float, or SamplingConfig
    target=None,
    groupby=None,
    time=None,
    engine="auto",            # auto, pandas, polars, arrow, duckdb
    plots=True,
    relationships="auto",     # none, light, auto, deep
    parquet_metadata=True,
    explain=True,
)
```

Modes:

- `quick`: metadata, schema, missingness, cheap column summaries.
- `standard`: most column stats, key plots, sampled relationships.
- `deep`: advanced diagnostics, relationship scans, drift-ready artifacts.
- `metadata`: Parquet/file/schema only, no full row scan.

### `scan`

Fast scan when the user wants lightweight facts before full profiling.

```python
scan = sf.scan("data/events/*.parquet")
scan.summary()
scan.schema()
scan.storage()
scan.issues()
```

This should be especially good for Parquet.

### `compare`

Compare two datasets or two profiles.

```python
diff = sf.compare("data/train.parquet", "data/test.parquet")
diff.summary()
diff.issues()
diff.plot("drift")
diff.plot("quantile_diff", column="revenue")
```

Options:

```python
diff = sf.compare(
    baseline,
    current,
    mode="standard",
    on=None,
    time=None,
    target=None,
    sample=100_000,
)
```

### `plot`

Direct plotting for users who know what they want.

```python
sf.plot(df, "histogram", column="revenue")
sf.plot(df, "lorenz", column="revenue")
sf.plot(df, "concentration", value="revenue", by="customer_id")
sf.plot(df, "qq", column="revenue", distribution="lognormal")
sf.plot(df, "missingness")
sf.plot(df, "correlation")
sf.plot(df, "target_rate", column="state", target="churned")
```

The same call should also work from a profile:

```python
profile.plot("lorenz", column="revenue")
```

### `suggest`

Convert observed data shape into next actions.

```python
sf.suggest(df, "types")
sf.suggest(df, "checks")
sf.suggest(df, "features")
sf.suggest(df, "plots")
sf.suggest(df, "cleaning")
```

Examples:

```python
profile.suggest("checks", format="pandera")
profile.suggest("checks", format="great_expectations")
profile.suggest("transforms")
profile.suggest("joins", other=customers)
```

### `report`

Simple report generation.

```python
sf.report(df, "report.html")
sf.report(profile, "report.md")
```

Options:

```python
sf.report(
    profile,
    "report.html",
    sections=["summary", "issues", "missingness", "distributions", "relationships"],
    theme="light",
    include_code=True,
    include_methods=True,
)
```

## Presets

Presets make the large feature catalog approachable.

```python
sf.profile(df, preset="first-look")
sf.profile(df, preset="parquet-audit")
sf.profile(df, preset="modeling")
sf.profile(df, preset="quality")
sf.profile(df, preset="drift")
sf.profile(df, preset="text")
sf.profile(df, preset="time-series")
```

Preset meanings:

- `first-look`: fast, broad, low-noise.
- `deep-eda`: advanced metrics and richer plots.
- `parquet-audit`: storage, schema, row groups, partition skew.
- `modeling`: target-aware summaries, leakage hints, feature suggestions.
- `quality`: rule hints, missingness, invalid values, contract suggestions.
- `drift`: comparison-oriented metrics.
- `publication`: cleaner plots and explainable method notes.

## Diagnostics As Lenses

Instead of exposing hundreds of top-level functions, group capabilities into
lenses.

```python
profile.lens("distribution").summary("revenue")
profile.lens("concentration").plot("revenue")
profile.lens("missingness").matrix()
profile.lens("relationships").top()
profile.lens("quality").issues()
profile.lens("parquet").storage()
profile.lens("grain").keys()
```

Core lenses:

- `overview`
- `schema`
- `storage`
- `types`
- `distribution`
- `concentration`
- `missingness`
- `relationships`
- `multivariate`
- `outliers`
- `quality`
- `drift`
- `target`
- `text`
- `time`
- `geo`
- `grain`
- `contracts`

This naming matches the product: `stateframe` gives the user different lenses.

## Function Naming Rules

- Use nouns for result objects: `Profile`, `ColumnProfile`, `Issue`, `PlotSpec`.
- Use verbs for user actions: `profile`, `scan`, `compare`, `plot`, `suggest`,
  `report`.
- Use plain English diagnostic names: `lorenz`, `pareto`, `qq`, `missingness`,
  `target_rate`.
- Use aliases for common terms:
  - `lorenz` and `concentration`.
  - `ecdf` and `cumulative`.
  - `boxen` and `letter_value`.
  - `kurtosis` and common misspelling `curtosis` as a friendly alias if desired.
- Keep advanced statistical method names available but not required.

## Progressive Disclosure

The user should be able to start simple:

```python
sf.profile(df)
```

Then ask for detail:

```python
profile.column("revenue").metrics()
```

Then ask for a specific advanced view:

```python
profile.column("revenue").plot("mean_excess")
```

Then tune the method:

```python
profile.plot(
    "mean_excess",
    column="revenue",
    threshold_grid="quantiles",
    min_quantile=0.80,
)
```

## Output Philosophy

Default methods should return displayable but inspectable objects.

```python
summary = profile.summary()
issues = profile.issues()
fig = profile.plot("histogram", column="revenue")
```

In a notebook:

- `summary` displays as a clean table.
- `issues` displays as a ranked issue table.
- `fig` displays as a plot.

In a script:

- objects can be printed.
- objects can be serialized.
- plots can be saved.

In a terminal:

- use Rich tables.
- keep output short by default.

## Configuration

Global config:

```python
sf.set_options(
    max_rows_for_exact=1_000_000,
    default_sample=100_000,
    plot_backend="matplotlib",
    display="auto",
)
```

Per-call config:

```python
profile = sf.profile(
    df,
    config={
        "numeric.quantiles": [0.01, 0.05, 0.5, 0.95, 0.99],
        "relationships.max_columns": 100,
        "plots.max_categories": 30,
    },
)
```

Typed config classes later:

```python
from stateframe import ProfileConfig

config = ProfileConfig(
    mode="deep",
    sample=250_000,
    correlations=["pearson", "spearman", "distance"],
    concentration=True,
)
```

## Metric Registry

Internally, metrics should be registered with metadata.

Each metric should define:

- id.
- display name.
- description.
- input types.
- required columns.
- backend support.
- exact or approximate support.
- computational cost.
- output schema.
- interpretation notes.
- issue rules.

Example:

```python
Metric(
    id="numeric.kurtosis",
    name="Kurtosis",
    applies_to=["numeric"],
    cost="cheap",
    output="scalar",
    interpretation="Tail weight relative to a normal-like distribution.",
)
```

Why this matters:

- Reports can explain metrics automatically.
- Users can discover metrics.
- Backends can advertise support.
- Tests can validate output schemas.
- We can add advanced methods without bloating the public API.

## Plot Registry

Plots should be registered like metrics.

Each plot should define:

- id.
- aliases.
- required data.
- compatible semantic types.
- required metrics.
- renderer support.
- default sampling strategy.
- interpretation notes.
- related plots.

Example:

```python
Plot(
    id="concentration.lorenz",
    aliases=["lorenz", "concentration"],
    columns={"value": "numeric"},
    default_renderer="matplotlib",
    interpretation="Shows how concentrated a total is across observations.",
)
```

This lets users call either:

```python
sf.plot(df, "lorenz", column="revenue")
```

or:

```python
profile.lens("concentration").plot("lorenz", column="revenue")
```

## Backend Architecture

Use adapters so the rest of the library does not care whether data is pandas,
Polars, Arrow, DuckDB, or Parquet metadata.

Backend interface:

```python
class Backend:
    def schema(self) -> SchemaSummary: ...
    def count_rows(self) -> int | None: ...
    def summarize_column(self, column: str, metrics: list[str]) -> dict: ...
    def value_counts(self, column: str, limit: int | None = None) -> Table: ...
    def quantiles(self, column: str, probs: list[float]) -> dict[float, float]: ...
    def sample(self, strategy: SamplingConfig) -> DataFrameLike: ...
```

Important design choice:

- Parquet metadata is a backend, not a side note.
- DuckDB can power many large-data summaries without loading into pandas.
- PyArrow can inspect schema and metadata.
- pandas can be the simplest first backend.

## Exact, Approximate, And Metadata-Only Results

Every result should identify its computation mode:

```python
{
    "metric": "distinct_count",
    "value": 184231,
    "mode": "approximate",
    "method": "hyperloglog",
    "relative_error": 0.01,
}
```

Modes:

- `exact`: scanned all needed data.
- `approximate`: sketch, sample, or approximate algorithm.
- `sampled`: based on row sample.
- `metadata`: based on file/schema/statistics metadata.
- `inferred`: semantic inference or heuristic.

This is central to trust.

## Issue Engine

The issue engine converts metrics into ranked findings.

Example rules:

- If `null_ratio > 0.95`, flag mostly missing.
- If `distinct_ratio == 1.0` and name looks like id, suggest identifier.
- If numeric column is float but all non-null values are integer-like, suggest
  integer or categorical review.
- If top 1 percent of rows contribute more than 80 percent of total, suggest
  concentration review.
- If Parquet files have severe row count skew, suggest storage repartitioning.
- If train/test PSI is high, flag drift.

Rules should be transparent and overrideable.

```python
profile.issues()
profile.issues(category="quality")
profile.issues(severity=["warning", "error"])
profile.issues(columns=["revenue"])
```

## Report Design

Reports should not be a giant wall of plots. They should be layered:

1. What should I look at first?
2. What is the dataset shape?
3. What is risky?
4. What is interesting?
5. What changed?
6. What should I do next?
7. What methods were used?

Report sections:

- Summary.
- Top issues.
- Dataset shape.
- Storage shape.
- Schema.
- Missingness.
- Distribution highlights.
- Concentration highlights.
- Relationship highlights.
- Outlier highlights.
- Target-aware highlights.
- Suggested checks.
- Appendix with all metrics.

## CLI Design

The CLI should be useful before someone writes Python.

```powershell
stateframe scan data/*.parquet
stateframe profile data/*.parquet --out report.html
stateframe compare baseline/*.parquet current/*.parquet --out drift.html
stateframe schema data/*.parquet
stateframe issues data/*.parquet
```

Useful flags:

```powershell
--mode quick|standard|deep|metadata
--sample 100000
--target churned
--time event_ts
--group customer_segment
--format html|md|json
--engine auto|pandas|polars|duckdb|arrow
```

## Examples To Build Early

### First Look

```python
import stateframe as sf

profile = sf.profile(df)
profile.summary()
profile.issues()
```

### Parquet Audit

```python
profile = sf.profile("events/date=*/part-*.parquet", mode="metadata")
profile.lens("storage").summary()
profile.lens("parquet").issues()
```

### Concentration

```python
profile = sf.profile(df)
profile.plot("lorenz", column="revenue")
profile.plot("pareto", column="customer_id", value="revenue")
```

### Train/Test Drift

```python
diff = sf.compare(train, test, target="churned")
diff.summary()
diff.issues()
diff.plot("drift", column="monthly_spend")
```

### Suggested Contract

```python
contract = profile.suggest("checks", format="pandera")
contract.save("schema.py")
```

## MVP Implementation Plan

### Phase 1: Package Skeleton

- Create `pyproject.toml`.
- Create `src/stateframe`.
- Create public API stubs.
- Add tests.
- Add README.
- Add CLI skeleton.

### Phase 2: Pandas Profile

- Dataset summary.
- Column type detection.
- Numeric stats.
- Categorical stats.
- Datetime stats.
- Missingness stats.
- Basic issue ranking.
- JSON export.

### Phase 3: Plot Basics Plus Differentiators

- Histogram.
- Box plot.
- ECDF.
- Q-Q plot.
- Missingness bar/matrix.
- Correlation heatmap.
- Lorenz curve.
- Pareto chart.
- Concentration curve.

### Phase 4: Parquet Metadata Scan

- File discovery.
- Schema scan.
- Row count from metadata.
- Row group stats.
- File size skew.
- Partition summary.
- Schema drift.
- Storage issue ranking.

### Phase 5: Compare

- Profile diff.
- Schema diff.
- Missingness diff.
- Numeric distribution diff.
- Categorical frequency diff.
- Drift scores.
- Comparison report.

### Phase 6: Contracts

- Suggested type rules.
- Suggested nullability rules.
- Suggested uniqueness rules.
- Suggested range rules.
- Pandera export.
- YAML export.

## API Boundaries

Keep these separate:

- Profiling computes facts.
- Issue ranking interprets facts.
- Plotting visualizes facts.
- Reporting arranges facts.
- Contracts turn facts into reusable checks.

This prevents the library from becoming one giant report function.

## What To Avoid

- Do not make the first screen a giant HTML-only profiler.
- Do not make users remember dozens of separate function names.
- Do not silently sample without saying so.
- Do not present p-values without effect sizes or context.
- Do not imply causality from EDA.
- Do not make plotting dependencies mandatory.
- Do not force pandas for Parquet metadata-only workflows.
- Do not bury the best findings below hundreds of trivial metrics.

## Names And Branding

Package:

```text
stateframe
```

Import:

```python
import stateframe as sf
```

CLI:

```powershell
stateframe profile data.parquet
```

Tagline options:

- See the shape of your data.
- A sharper first look at data.
- Exploratory data analysis with better lenses.
- DataFrame and Parquet EDA that finds what matters.

## Definition Of Great

`stateframe` is great if:

- A beginner can run it in one line.
- An experienced data scientist discovers issues they would otherwise miss.
- A large Parquet dataset can be understood before loading everything.
- The report explains why each finding matters.
- The API makes advanced EDA feel ordinary.
- Results can be saved, compared, and turned into checks.
- The library helps users move from curiosity to decision.
