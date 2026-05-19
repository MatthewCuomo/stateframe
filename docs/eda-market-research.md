# stateframe Market Research

Research date: 2026-05-07

This document surveys Python EDA, profiling, dataframe exploration,
visualization, drift, and data-quality libraries that overlap with `stateframe`.
The goal is to find a lane where `stateframe` is useful without becoming another
one-line HTML profiler.

This is a practical market snapshot, not a legal or academic claim that every
small or abandoned PyPI package has been found. The Python EDA long tail is
large. The important pattern is clear: most tools either make a static report,
open a GUI, provide quick summaries, specialize in missingness, or validate data
quality. Very few treat "data shape" as a first-class, reusable, Parquet-aware,
diffable, explainable object.

## Executive Takeaway

The obvious lane for `stateframe` is not "generate an automated EDA report."
That lane is crowded.

The better lane is:

> Local, dataframe-and-Parquet EDA that produces reusable data-shape profiles,
> advanced diagnostic lenses, issue rankings, dataset comparisons, and suggested
> checks through a small Python interface.

Where `stateframe` can be different:

- Parquet-native profiling before loading the full dataset.
- Storage-shape diagnostics: files, row groups, partition skew, compression,
  schema drift, min/max/null statistics, predicate-pushdown usefulness.
- Data-shape language: grain, keys, entity/event hints, concentration, sparsity,
  semantic types, drift, duplicate structure, joinability.
- Advanced but practical plots: Lorenz/concentration curves, Pareto/ABC curves,
  ECDF/CCDF, Q-Q/P-P, shift functions, missingness co-occurrence, heavy-tail
  diagnostics, grouped distribution differences.
- Diffable profiles: compare train/test, baseline/current, before/after cleaning,
  or month-over-month Parquet snapshots.
- EDA-to-contract output: suggested Pandera, Great Expectations, YAML, or dbt-like
  checks.
- A plot/spec registry that can render with existing plotting libraries instead
  of trying to own every pixel from day one.

## Competitive Categories

### One-Line Profilers And HTML Reports

These tools promise "run one command, get a report."

| Tool | What it offers | Strength | Gaps for `stateframe` to exploit |
| --- | --- | --- | --- |
| [YData Profiling](https://docs.profiling.ydata.ai/latest/) | One-line profile reports with statistics, visualizations, data-quality alerts, missingness, correlations, interactions, time-series support, dataset comparison, JSON export, and Spark support. | The category leader. Comprehensive, familiar, shareable HTML reports. | Still centered on report generation. Large data guidance often uses minimal mode or sampling. It does not appear focused on Parquet storage-shape diagnostics, grain/key inference, or reusable advanced diagnostic lenses. |
| [Sweetviz](https://pypi.org/project/sweetviz/) | High-density HTML EDA reports with target analysis, train/test or subgroup comparison, mixed-type associations, type inference, summary statistics, skewness, kurtosis, missingness, frequent values, and correlations. | Excellent "first report" and comparison workflow. Strong target-oriented EDA. | Pandas-centric report tool. Less suited to Parquet metadata, reusable profile artifacts, advanced statistical plot catalog, or backend-agnostic profiling. |
| [DataPrep.EDA](https://docs.dataprep.ai/user_guide/eda/introduction.html) | Task-centric functions: `plot()`, `plot_correlation()`, `plot_missing()`, `plot_diff()`, and `create_report()`. Supports distribution, relationship, missingness, and dataset-difference views. | Clean task-based interface. Good missingness and difference workflows. | Its core abstraction is still plotting/reporting around pandas/Dask-style dataframes. Less emphasis on storage metadata, contracts, grain, semantic shape, or advanced diagnostic catalog. |
| [AutoViz](https://github.com/AutoViML/AutoViz) | One-line automatic visualization for files or pandas DataFrames. Handles chart generation, large-dataset sampling, target variable, multiple chart formats, Bokeh/HTML/server output, and data quality/FixDQ features. | Strong automated visual generation with many output modes. | More visualization automation than profile intelligence. Less focused on composable metrics, profile diffing, Parquet metadata, or advanced EDA diagnostics beyond common plots. |
| [edaflow](https://pypi.org/project/edaflow/) | EDA workflow package with missing-data analysis, categorical insights, type conversion, histograms, boxplots, heatmaps, scatter matrix, rich output, dark-mode notebook compatibility, profiling report, and ML workflow helpers. | Broad beginner-friendly workflow. Recent and actively updated. | Expands into ML workflow and education. `stateframe` can stay sharper: storage-aware, advanced EDA, profile artifacts, and diagnostics instead of end-to-end ML helper. |
| [turboeda](https://pypi.org/project/turboeda/) | One-command CSV/XLSX EDA report generator using pandas, Plotly, Jinja2, Typer, chardet, and openpyxl. Produces polished interactive HTML reports with themes, sampling, correlation limits, and per-variable chart caps. | Simple CLI and nice report-generation story. | File/report oriented. No obvious Parquet-native or profile-object angle. |
| [eda-profiler](https://pypi.org/project/eda-profiler/) | Lightweight pandas DataFrame profiler. Computes missing values, numerical descriptive stats, percentiles, skewness, kurtosis, IQR, coefficient of variation, zeros, categorical cardinality, mode, and top-level summary. | Simple and focused. | Basic summary table, not a full EDA system. No plots, Parquet, profile diffs, issue engine, or advanced lenses. |
| [PySuricata](https://pypi.org/project/pysuricata/0.0.12/) | Lightweight EDA profiler with streaming architecture, bounded memory, single-pass algorithms, exact moments, approximate distinct/frequency algorithms, pandas/polars dependency story, and self-contained HTML reports. | Interesting technical direction: streaming and scalable profiles. | Currently positioned as a lightweight HTML profiler. `stateframe` can learn from streaming metrics but differentiate with Parquet metadata, shape interpretation, advanced diagnostics, contracts, and plot registry. |
| [pandas-eda](https://pypi.org/project/pandas-eda/) | Adds `df.eda()` to show dataframe status and frequent values in a web application, useful during debugging. | Convenient dataframe-status check. | Narrower than our goal. |
| [EDAeasy](https://pypi.org/project/EDAeasy/) | Quick pandas summary function with dtype, min, max, NaN percentage, unique count, and unique values. | Tiny and approachable. | Too small/simple to occupy the `stateframe` lane. |
| [edakit](https://pypi.org/project/edakit/) | Marketed as EDA toolkit, but PyPI description shows text sentiment analysis examples. | Name overlap only. | Not a serious EDA competitor based on public metadata. |
| [edabox](https://pypi.org/project/edabox/) | PyPI summary says "Python Library to Gain Insight into Datasets," but no public project description is provided. | Name and positioning overlap. | Sparse public package info. Not a clear feature competitor. |

### Interactive Dataframe Explorers And GUIs

These tools make data interactive through a UI.

| Tool | What it offers | Strength | Gaps for `stateframe` to exploit |
| --- | --- | --- | --- |
| [D-Tale](https://github.com/man-group/dtale) | Flask/React visualizer for pandas data structures with table browsing, filtering, charts, code export, correlations, PPS, missing-data side panels, timeseries correlation views, and many dataframe operations. | Very powerful dataframe GUI. Great for manual inspection. | Heavy UI product. `stateframe` can be lighter, local-code-first, profile/report/object-first, and Parquet-aware. |
| [Lux](https://lux-api.readthedocs.io/en/latest/source/getting_started/overview.html) | Automatic dataframe visualization recommendations in notebooks. Printing a dataframe can show recommended visualizations for interesting patterns and trends. | Excellent idea: recommendation and intent-based visual EDA. | Focused on visualization recommendations, not a full profile/quality/storage/contract system. |
| [PyGWalker](https://pygwalker-docs.vercel.app/) | Turns pandas or Polars dataframes into a Tableau-style UI for visual exploration. | Strong no-code visual analysis workflow. | UI-first. Does not seem centered on reusable metrics, Parquet metadata, issue ranking, or contracts. |
| [PandasGUI](https://github.com/SayonB/pandasgui) | PyQt GUI for viewing and analyzing pandas DataFrames, with dataframe viewer, statistics, histogram viewer, and interactive graphing. | Familiar GUI experience for pandas tables. | Desktop GUI focus. Less useful for headless scripts, CI, stored profiles, Parquet scans, and report artifacts. |
| [Mito](https://docs.trymito.io/) | Jupyter spreadsheet for pandas workflows. Supports edits, filters, pivots, graphs, and generated pandas code. Mito AI adds LLM-assisted transformations. | Strong spreadsheet-to-code workflow. | More wrangling and spreadsheet workflow than EDA diagnostics. Some AI features involve external API/cloud concerns. |
| [bamboolib](https://pypi.org/project/bamboolib/) | GUI for pandas DataFrames in Jupyter/JupyterLab. Databricks docs describe no-code analysis, transformations, visualizations, and generated Python code. | No-code data wrangling and exploration. | Commercial/platform-adjacent and GUI-oriented. Not a local lightweight profile engine. |
| [VisiData](https://www.visidata.org/) | Terminal multitool for tabular data with spreadsheet-like exploration, many formats, histograms, scatterplots, large-file interaction, and session replay. | Excellent terminal exploration. Fast and practical. | Not a Python library interface for generating reusable EDA profiles and plots in notebooks/reports. |
| [Orange](https://oldorange.biolab.si/home/visual-_programming/) | Visual programming tool for data mining, visualization, analysis, and machine learning through connected widgets. | Strong for education, no-code ML, and visual workflows. | Separate desktop/workflow environment, not a small Python EDA library. |
| [PyAnalytica](https://pypi.org/project/pyanalytica/) | Interactive analytics workbench with dataframe profiling, filtering, transformations, charts, statistical tests, modeling, and "Show Code" teaching workflow. | Broad teaching/data-science workbench. | Not narrowly focused on data-shape profiling or Parquet. Large surface area. |

### Lightweight Summary And Focused EDA Helpers

These tools solve one or two common EDA pains.

| Tool | What it offers | Strength | Gaps for `stateframe` to exploit |
| --- | --- | --- | --- |
| [skimpy](https://aeturrell.github.io/skimpy/) | Console/Jupyter summary statistics for pandas and Polars DataFrames. Alternative to `DataFrame.describe()`. Has CLI. | Lightweight, fast, Polars-friendly. | Summary table only. No deep diagnostics, Parquet metadata, issue ranking, or plot catalog. |
| [missingno](https://github.com/ResidentMario/missingno) | Missing-data visualizations: matrix, bar, heatmap, dendrogram. Dendrogram clusters variables by nullity correlation. | Best-known missingness visualization specialist. | Single domain. `stateframe` can include missingness as one lens, with more integration and issue interpretation. |
| [klib](https://klib.readthedocs.io/en/stable/index.html) | Data importing, cleaning, analyzing, preprocessing. Includes categorical plots, correlation matrices/heatmaps, distribution plots, missing-value plots, dtype conversion, duplicate/empty row/column cleanup. | Practical cleaning plus EDA helpers. | Function collection rather than profile system. Less advanced/statistical/storage-focused. |
| [dabl](https://dabl.github.io/stable/) | Data Analysis Baseline Library. Helps with supervised ML exploration and baselines; `plot(X, y)` finds useful visualizations, pairplots, categorical impacts, LDA projections, and simple models. | Good target-aware EDA for modeling. | ML-baseline oriented. Less useful for general data-shape, storage, Parquet, contracts, and non-target EDA. |
| [ppscore](https://pypi.org/project/ppscore/) | Predictive Power Score: asymmetric, data-type-agnostic relationship score that can detect linear or nonlinear predictive relationships. | Useful alternative/complement to correlations. | Relationship metric, not full EDA library. Could be an optional relationship lens dependency. |
| [PhiK](https://phik.readthedocs.io/) | Phi_K correlation coefficient for categorical, ordinal, and interval variables; captures nonlinear dependency and includes significance/outlier functionality. | Powerful mixed-type association statistics. | Specialized metric package. `stateframe` can wrap or integrate the idea. |
| [dython](https://shakedzy.xyz/dython/modules/nominal/) | Mixed-type association tools: Pearson for numeric-numeric, correlation ratio for categorical-numeric, Cramer's V or Theil's U for categorical-categorical, association heatmaps. | Useful for mixed-type relationship scans. | Focused on associations, not whole-dataset profiling. |
| [DataComPy](https://pypi.org/project/datacompy/) | Compares two DataFrames/tables across pandas, Spark, Polars, Snowflake, Dask, DuckDB via Fugue. Reports row/column/value differences with tolerances. | Strong row-level dataframe comparison. | Comparison is equality/diff oriented, not distributional EDA drift or profile diffing. |

### Drift, Monitoring, Data Quality, And Contracts

These are adjacent. They often matter after EDA becomes productionized.

| Tool | What it offers | Strength | Gaps for `stateframe` to exploit |
| --- | --- | --- | --- |
| [Evidently](https://docs.evidentlyai.com/) | Open-source Python library for tabular data quality, data drift, ML checks, reports, and tests. Data drift preset compares reference/current distributions and chooses drift methods by column type. | Strong drift/monitoring story. | More monitoring/evaluation than exploratory "first look." Less focused on Parquet storage shape or advanced EDA plot menu. |
| [whylogs](https://docs.whylogs.com/en/latest/features/profiling.html) | Lightweight, scalable, mergeable data profiles generated in one pass with minimal memory overhead. Designed for logging, monitoring, constraints, and rare-event capture. | Excellent scalable profile architecture. | Monitoring/profile logging more than notebook EDA. Less visual/interpretive by default. |
| [Deepchecks](https://docs.deepchecks.com/stable/tabular/index.html) | Tabular checks and suites for data integrity, train/test validation, and model evaluation. | Strong ML validation check catalog. | Check/suite framework rather than exploratory data-shape library. |
| [Great Expectations](https://docs.greatexpectations.io/docs/core/connect_to_data/dataframes) | Data quality expectations, validation, checkpoints, data docs, dataframe support for pandas and Spark. | Industry-known validation/documentation framework. | Setup and mental overhead can be high for initial EDA. Better as an export target than a direct competitor. |
| [Pandera](https://pandera.readthedocs.io/) | DataFrame schema validation across pandas, Polars, PySpark, Ibis, etc. Supports checks, schema inference, lazy validation, and typed dataframe models. | Excellent dataframe contract system. | Validation-first. `stateframe` should generate suggested Pandera schemas rather than compete. |
| [Soda Core](https://docs.soda.io/soda-core/overview-main.html/) | Open-source Python/CLI data quality checks using SodaCL, connecting to many data sources and translating checks to SQL. | Strong data-engineering data-quality checks. | SQL/data quality focus, not exploratory EDA diagnostics. |
| [PyDeequ](https://pypi.org/project/pydeequ/) | Python API for Deequ on Spark; "unit tests for data," analyzers, constraints, profile results, verification suites. | Strong Spark-scale data quality. | Spark/data-quality oriented. Not a first-look DataFrame/Parquet EDA package. |
| [Frictionless Framework](https://framework.frictionlessdata.io/docs/guides/describing-data.html) | Describes, extracts, validates, and transforms tabular data; can infer schemas and metadata, validate resources/packages, and produce reports. | Strong metadata and data package concepts. | General data-management framework, not rich statistical EDA. |

### Big Data And Parquet-Oriented Building Blocks

These are not EDA competitors in the same way, but they are important backend
inspiration for `stateframe`.

| Tool | What it offers | Why it matters |
| --- | --- | --- |
| [DuckDB](https://duckdb.org/docs/stable/data/parquet/metadata) | Reads Parquet efficiently and exposes `parquet_metadata`, `parquet_schema`, `parquet_file_metadata`, min/max/null counts, compression, encodings, row-group info, and Bloom filter probes. | This is one of the best engines for `stateframe` Parquet storage-shape scans. |
| [PyArrow](https://arrow.apache.org/docs/python/parquet.html) | Python bindings for Arrow/Parquet reading, writing, schemas, file metadata, datasets, and columnar compute. | Natural foundation for schema, metadata, and dataframe interchange. |
| [Polars](https://huggingface.co/docs/hub/datasets-polars) | Lazy/eager dataframe library; `scan_parquet` supports lazy query optimization, predicate pushdown, and projection pushdown. | Important for modern DataFrame users and large local data. |
| [Vaex](https://vaex.io/docs/index.html) | Lazy, out-of-core DataFrames for huge tabular data, fast statistics, histograms, density plots, and interactive exploration. | Shows the value of binned statistics and lazy computation for large data. |

## What The Market Already Does Well

- One-line summary/report generation.
- Common numerical stats: mean, std, min, max, quartiles, missingness, skewness,
  kurtosis.
- Common categorical stats: top values, cardinality, frequencies.
- Missingness bars, matrices, heatmaps, and dendrograms.
- Correlation heatmaps.
- Basic train/test or before/after comparisons.
- Target-aware summaries for classification/regression.
- GUI-based dataframe browsing.
- Interactive chart exploration.
- Data-quality checks and validation.
- Drift monitoring for production ML.

## What The Market Does Not Seem To Own

These are promising `stateframe` lanes.

### 1. Parquet-Native EDA

Most EDA libraries assume the data is already loaded into pandas, or they sample
large data. `stateframe` can make Parquet metadata itself part of EDA:

- File count, size distribution, row counts, row groups.
- Schema drift across files.
- Partition skew.
- Column chunk sizes.
- Compression and encoding patterns.
- Row-group min/max/null stats.
- Predicate-pushdown usefulness.
- Small-file and oversized-row-group warnings.
- Metadata-only profile mode.

This is especially valuable for data scientists who receive a "dataset" that is
actually a directory of Parquet files.

### 2. Data Shape, Not Just Column Stats

The phrase "shape" should mean more than rows x columns:

- What does one row represent?
- Are there candidate keys?
- Are there duplicate entities or duplicate events?
- Which columns look like identifiers, measures, dimensions, timestamps, targets,
  probabilities, residuals, or leakage?
- Is the table a fact table, dimension table, event log, snapshot, feature matrix,
  panel, or report output?
- Are there join keys and join explosion risks?

Very few tools speak this language explicitly.

### 3. Advanced Diagnostic Lenses

Most tools cover histograms, boxplots, and correlations. `stateframe` can make
advanced but practical diagnostics easy:

- Lorenz curve.
- Concentration curve.
- Pareto and ABC curves.
- ECDF and CCDF.
- Q-Q, P-P, and detrended Q-Q plots.
- Cullen-Frey skewness/kurtosis plot.
- Mean excess and Hill plots for heavy tails.
- Shift function and quantile-difference plots.
- Missingness co-occurrence and block maps.
- Mixed-type association scans.
- Robust effect sizes, not just p-values.

The point is not to dump obscure statistics on users. The point is to package
them as named lenses with plain-English interpretation.

### 4. Reusable Profile Artifacts

One-line HTML reports are helpful, but they are often dead ends. `stateframe`
profiles should be objects and files that can be:

- Compared.
- Versioned.
- Exported to JSON.
- Rendered to Markdown or HTML.
- Converted into validation checks.
- Used by downstream code.
- Computed exactly, approximately, or from metadata, with that mode preserved.

### 5. EDA-To-Contract

A powerful workflow:

```python
profile = sf.profile("data/*.parquet")
profile.issues()
profile.suggest("checks", format="pandera")
profile.suggest("checks", format="great_expectations")
```

This turns first-look EDA into reusable data quality.

## Plotting And Visualization Strategy

Short answer: yes, `stateframe` can and should lean on existing plotting packages.
When someone installs `stateframe`, the plotting code can call local Python
libraries like Matplotlib, Seaborn, Plotly, or Altair. This is not an internet
API. The code runs in the user's Python process.

### Existing Plotting Packages Worth Leaning On

| Library | Best for | Notes |
| --- | --- | --- |
| [Matplotlib](https://matplotlib.org/stable/api/axes_api.html) | Stable static plots, PNG/SVG/PDF output, deep customization. | Uses `Figure` and `Axes` objects. Great baseline backend. |
| [Seaborn](https://seaborn.pydata.org/) | Statistical plots on top of Matplotlib. | Good defaults for distributions, categorical plots, regression plots, heatmaps. |
| [Plotly](https://plotly.com/python/graph-objects/) | Interactive HTML plots. | Uses `Figure` objects with traces and layout. Great for reports. |
| [Altair](https://altair-viz.github.io/index.html) | Declarative visualization specs based on Vega-Lite. | Good fit for a plot-spec architecture and notebook display. |
| Bokeh/hvPlot/Datashader | Large interactive plots and dashboards. | Better as later optional extras. |

### How A Python Library Makes A Plot

At the simplest level, a function receives data and returns a figure object:

```python
def histogram(df, column):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.hist(df[column].dropna(), bins=40)
    ax.set_title(f"Distribution of {column}")
    return fig
```

That is enough for a first version.

But for `stateframe`, the better design is layered:

1. Compute metrics.
2. Build visualization-ready data.
3. Create a backend-neutral plot specification.
4. Render that specification with Matplotlib, Plotly, Altair, etc.
5. Return the rendered figure, but keep the spec for reports and tests.

Example public interface:

```python
profile = sf.profile(df)

profile.plot("histogram", column="revenue")
profile.plot("lorenz", column="revenue")
profile.plot("qq", column="revenue", distribution="lognormal")
profile.plot("missingness")

profile.plot("lorenz", column="revenue", backend="plotly")
profile.plot("lorenz", column="revenue", backend="matplotlib")
```

Example internal design:

```python
spec = profile.plot_spec("lorenz", column="revenue")
fig = sf.render(spec, backend="matplotlib")
```

Potential `PlotSpec` shape:

```python
PlotSpec(
    kind="concentration.lorenz",
    title="Revenue concentration",
    data=plot_data,
    encodings={
        "x": "cumulative_share_of_rows",
        "y": "cumulative_share_of_revenue",
    },
    layers=[
        {"mark": "line", "role": "lorenz_curve"},
        {"mark": "line", "role": "equality_reference"},
    ],
    annotations=[
        {"text": "Top 10% contribute 72% of revenue", "x": 0.9, "y": 0.28}
    ],
    method_notes=[
        "Rows sorted by revenue ascending.",
        "Missing and negative values were excluded by default.",
    ],
)
```

### Should We Build Plotting From Scratch?

Not for version 1.

Building a plotting engine from scratch means implementing:

- Marks: points, lines, bars, areas, boxes, violins, density bands.
- Scales: linear, log, categorical, time, quantile.
- Axes, ticks, labels, legends, titles.
- Layout, facets, small multiples, responsive sizing.
- Color palettes and accessibility.
- Tooltips, zoom, selection, interactivity.
- Export to PNG, SVG, HTML, PDF.
- Notebook rendering.
- Browser rendering.
- Testing across platforms.

That is a separate company-sized problem. The better move is to build our own
EDA intelligence and use existing renderers.

However, `stateframe` can own a small visualization layer:

- Plot recommendations.
- Plot specs.
- Statistical transforms.
- Consistent naming.
- Consistent annotations.
- Consistent "why this matters" explanations.
- Multiple renderers.
- Report layout.

So the recommendation is:

> Build our own plot intelligence, not our own plotting engine.

## Suggested Product Positioning

`stateframe` should not say:

> "Generate an EDA report in one line."

That sounds like YData Profiling, Sweetviz, AutoViz, and turbosf.

Better:

> "See the shape of DataFrames and Parquet datasets."

Or:

> "EDA profiles, diagnostics, and data-shape checks for DataFrames and Parquet."

The key message:

- Beginner-friendly first look.
- Advanced lenses when you need them.
- Parquet-aware before loading everything.
- Profiles you can diff, save, and turn into checks.

## Proposed MVP Based On Market Gaps

### MVP 1: Local Profile Object

```python
import stateframe as sf

profile = sf.profile(df)
profile.summary()
profile.columns()
profile.issues()
```

Must include:

- Dataset summary.
- Column summaries.
- Numeric stats including skewness and kurtosis.
- Missingness.
- Categorical concentration.
- Datetime summaries.
- Issue ranking.
- JSON export.

### MVP 2: Differentiating Plots

```python
profile.plot("histogram", column="revenue")
profile.plot("ecdf", column="revenue")
profile.plot("qq", column="revenue")
profile.plot("lorenz", column="revenue")
profile.plot("pareto", column="customer_id", value="revenue")
profile.plot("missingness")
profile.plot("correlation")
```

Use Matplotlib by default. Add Plotly as optional.

### MVP 3: Parquet Metadata Scan

```python
scan = sf.scan("data/sales/*.parquet", mode="metadata")
scan.storage()
scan.schema()
scan.issues()
```

Must include:

- File count and sizes.
- Row count from metadata.
- Row group counts.
- Schema consistency.
- Partition summary.
- Compression/encoding summary where available.
- Row-group min/max/null summary where available.
- Storage issues.

### MVP 4: Compare Profiles

```python
diff = sf.compare(train, test)
diff.summary()
diff.issues()
diff.plot("drift", column="revenue")
```

Must include:

- Schema diff.
- Missingness diff.
- Numeric quantile diff.
- Categorical frequency diff.
- Distribution distance scores.
- New/lost categories.

### MVP 5: Suggested Checks

```python
profile.suggest("checks")
profile.suggest("checks", format="pandera")
```

Start with:

- Type checks.
- Nullability checks.
- Range checks.
- Set checks for low-cardinality columns.
- Uniqueness checks.
- Composite-key hints later.

## What To Avoid

- Do not compete head-on as "yet another automated HTML report."
- Do not start with a heavy GUI.
- Do not make plotting dependencies mandatory.
- Do not pretend sampled metrics are exact.
- Do not lead with obscure statistics; package them as understandable lenses.
- Do not become an AutoML package.
- Do not send user data to a server.

## Working Hypothesis

The `stateframe` wedge is:

```python
profile = sf.profile("events/date=*/part-*.parquet", mode="standard")

profile.summary()
profile.lens("storage").issues()
profile.lens("concentration").plot("revenue")
profile.lens("grain").keys()
profile.suggest("checks", format="pandera")
```

This is meaningfully different from the current market because it combines:

- A simple local Python interface.
- Parquet-aware data access.
- Advanced EDA made discoverable.
- Data-shape interpretation.
- Persistent/diffable profile artifacts.
- Practical next steps.

That is a lane worth building.

## Source Links

Core profilers and EDA tools:

- [YData Profiling docs](https://docs.profiling.ydata.ai/latest/)
- [YData large dataset docs](https://docs.profiling.ydata.ai/latest/features/big_data/)
- [Sweetviz PyPI](https://pypi.org/project/sweetviz/)
- [DataPrep.EDA docs](https://docs.dataprep.ai/user_guide/eda/introduction.html)
- [AutoViz GitHub](https://github.com/AutoViML/AutoViz)
- [D-Tale GitHub](https://github.com/man-group/dtale)
- [D-Tale docs](https://dtale.readthedocs.io/)
- [skimpy docs](https://aeturrell.github.io/skimpy/)
- [missingno GitHub](https://github.com/ResidentMario/missingno)
- [klib docs](https://klib.readthedocs.io/en/stable/index.html)
- [Lux docs](https://lux-api.readthedocs.io/en/latest/source/getting_started/overview.html)
- [PyGWalker docs](https://pygwalker-docs.vercel.app/)
- [dabl docs](https://dabl.github.io/stable/)
- [PandasGUI GitHub](https://github.com/SayonB/pandasgui)
- [Mito docs](https://docs.trymito.io/)
- [VisiData](https://www.visidata.org/)
- [Orange visual programming](https://oldorange.biolab.si/home/visual-_programming/)
- [edaflow PyPI](https://pypi.org/project/edaflow/)
- [turboeda PyPI](https://pypi.org/project/turboeda/)
- [eda-profiler PyPI](https://pypi.org/project/eda-profiler/)
- [PySuricata PyPI](https://pypi.org/project/pysuricata/0.0.12/)
- [pandas-eda PyPI](https://pypi.org/project/pandas-eda/)
- [EDAeasy PyPI](https://pypi.org/project/EDAeasy/)
- [edakit PyPI](https://pypi.org/project/edakit/)
- [edabox PyPI](https://pypi.org/project/edabox/)

Adjacent metrics, validation, and backend tools:

- [Evidently docs](https://docs.evidentlyai.com/)
- [whylogs profiling docs](https://docs.whylogs.com/en/latest/features/profiling.html)
- [Deepchecks tabular docs](https://docs.deepchecks.com/stable/tabular/index.html)
- [Great Expectations dataframe docs](https://docs.greatexpectations.io/docs/core/connect_to_data/dataframes)
- [Pandera docs](https://pandera.readthedocs.io/)
- [Soda Core docs](https://docs.soda.io/soda-core/overview-main.html/)
- [PyDeequ PyPI](https://pypi.org/project/pydeequ/)
- [Frictionless describing data docs](https://framework.frictionlessdata.io/docs/guides/describing-data.html)
- [ppscore PyPI](https://pypi.org/project/ppscore/)
- [PhiK docs](https://phik.readthedocs.io/)
- [dython docs](https://shakedzy.xyz/dython/modules/nominal/)
- [DataComPy PyPI](https://pypi.org/project/datacompy/)
- [DuckDB Parquet metadata docs](https://duckdb.org/docs/stable/data/parquet/metadata)
- [PyArrow Parquet docs](https://arrow.apache.org/docs/python/parquet.html)
- [Vaex docs](https://vaex.io/docs/index.html)

Plotting libraries:

- [Matplotlib Axes docs](https://matplotlib.org/stable/api/axes_api.html)
- [Seaborn docs](https://seaborn.pydata.org/)
- [Plotly graph objects docs](https://plotly.com/python/graph-objects/)
- [Altair docs](https://altair-viz.github.io/index.html)
