# Agentic EDA For stateframe

`stateframe` should not only describe a dataset. It should learn enough about the
dataset to guide the next move.

The big idea:

> Run a broad initial profile, infer the shape of the data, then recommend the
> next best EDA lenses based on what was found.

Different data shapes deserve different first questions. A time series needs
cadence, gaps, seasonality, and change-point checks. A transaction table needs
concentration, grain, duplicate events, and entity behavior. A wide feature
matrix needs sparsity, leakage, multicollinearity, target relationships, and
model-readiness checks. A Parquet directory needs storage shape before row-level
statistics. A nested JSON column needs schema-path profiling before ordinary
value counts.

Most EDA tools act like every dataset wants the same report. `stateframe` can be
better by acting like a careful data scientist: first observe broadly, then
choose the next useful question.

## Core Product Thesis

The winning EDA library should be:

- Broad enough to give a useful first look in one line.
- Intelligent enough to avoid showing the same wall of plots for every dataset.
- Honest about what it knows, how it knows it, and what is still uncertain.
- Able to recommend advanced diagnostics without requiring the user to remember
  their names.
- Able to turn discoveries into repeatable checks, reports, and future
  comparisons.

The core flow:

```python
import stateframe as sf

profile = sf.profile("events/date=*/part-*.parquet")

profile.summary()
profile.issues()
profile.recommendations()
```

Then:

```python
profile.recommendations().top(5)

profile.run("time.cadence")
profile.run("grain.keys")
profile.run("concentration.pareto", value="revenue", by="customer_id")
```

Or, with a more guided workflow:

```python
session = sf.explore("events/date=*/part-*.parquet", goal="first-look")

session.next()
session.run_next()
session.report("report.html")
```

This makes `stateframe` feel like a small library with an adaptive EDA brain.

## What Agentic Means Here

Agentic EDA does not need to mean an LLM controls the analysis.

In `stateframe`, "agentic" should mean a transparent planning loop:

1. Observe the dataset cheaply and broadly.
2. Infer likely data shapes and semantic types.
3. Form hypotheses about risks, opportunities, and useful next lenses.
4. Rank recommended analyses by expected value, confidence, urgency, and cost.
5. Let the user run one recommendation, several recommendations, or a budgeted
   automatic pass.
6. Feed new findings back into the profile and update recommendations.

The first implementation should be deterministic and explainable. Optional LLM
features can later improve narration, report wording, or natural-language goal
translation, but the core recommendation engine should work locally without
sending data anywhere.

## The Adaptive EDA Loop

### 1. Intake

Normalize input into a `DatasetRef`.

Inputs:

- pandas DataFrame.
- Polars DataFrame or LazyFrame.
- PyArrow Table or Dataset.
- DuckDB relation.
- Parquet file, directory, or glob.
- CSV or JSONL later.

The intake layer determines:

- Backend capabilities.
- Whether the data is eager or lazy.
- Whether metadata can answer some questions.
- Approximate rows, columns, and bytes.
- File and partition layout.
- Whether sampling is needed.
- Which operations are likely to be expensive.

### 2. Broad Initial Profile

The initial profile should gather enough evidence to route the user correctly.
It should not attempt every possible diagnostic.

Default first-pass profile:

- Dataset dimensions and storage shape.
- Schema and inferred semantic types.
- Missingness and completeness.
- Universal column metrics.
- Cheap numeric, categorical, datetime, boolean, and text summaries.
- Candidate identifiers, targets, timestamps, groups, and measures.
- Cardinality and concentration hints.
- Row grain and duplicate hints.
- Sampling diagnostics when sampled.
- Parquet metadata scan when applicable.
- Top issues and top opportunities.

The output is not just a report. It is an evidence object that future lenses can
reuse.

### 3. Shape Inference

The profile should infer dataset shape, not only column type.

Possible dataset shape hypotheses:

- `time_series`: one or more values observed over time.
- `event_log`: rows are events with timestamps and entities.
- `panel`: repeated observations across entities and time.
- `transaction_table`: rows are purchases, payments, orders, claims, or similar.
- `feature_matrix`: rows are entities or observations with many candidate
  features.
- `targeted_modeling_table`: a feature matrix with a target.
- `survey_table`: questionnaire-like columns with skip patterns and coded
  responses.
- `wide_sparse_matrix`: many columns, many missing or zero values.
- `text_corpus`: one or more text-heavy columns.
- `geospatial_points`: coordinate columns or geometry objects.
- `graph_edge_list`: source-target pairs with optional edge attributes.
- `nested_records`: JSON, struct, list, or map-heavy data.
- `parquet_dataset`: multi-file columnar dataset with storage concerns.
- `report_output`: already aggregated or pivoted table.
- `dimension_table`: one row per entity, often with keys and attributes.
- `fact_table`: many rows of measures keyed by dimensions.

Each shape hypothesis should include:

- Confidence.
- Evidence.
- Counter-evidence.
- Recommended next lenses.
- Risks if ignored.

Example:

```python
ShapeHypothesis(
    id="event_log",
    confidence=0.87,
    evidence=[
        "Column event_ts looks like an event timestamp.",
        "Column customer_id looks like an entity identifier.",
        "Rows are not unique by customer_id.",
        "Timestamps span 180 days and are not regular."
    ],
    recommended_lenses=["grain.events", "time.interarrival", "entity.activity"]
)
```

### 4. Recommendation Planning

The recommendation engine converts evidence into ranked next steps.

Each recommendation should answer:

- What should I run next?
- Why does this matter for this dataset?
- What evidence triggered it?
- What will it produce?
- How expensive is it?
- What can I do with the result?
- Is it exact, approximate, sampled, metadata-only, or inferred?

Example public display:

```text
1. Investigate event-time gaps
   Lens: time.cadence
   Why: event_ts is the dominant timestamp and has irregular spacing.
   Cost: low
   Output: gap table, cadence summary, missing time-window plot

2. Check customer revenue concentration
   Lens: concentration.pareto
   Why: revenue is positive and customer_id looks like an entity key.
   Cost: medium
   Output: Pareto chart, top-share metrics, concentration issue ranking

3. Audit Parquet partition skew
   Lens: storage.partition_skew
   Why: input is a partitioned Parquet dataset with uneven file sizes.
   Cost: metadata-only
   Output: partition summary, skew warnings, repartition suggestions
```

### 5. Lens Execution

A lens is a focused diagnostic module.

Examples:

- `time.cadence`
- `time.seasonality`
- `grain.keys`
- `grain.duplicates`
- `quality.missingness`
- `quality.type_coercion`
- `concentration.lorenz`
- `concentration.pareto`
- `distribution.heavy_tail`
- `relationships.mixed_associations`
- `target.leakage`
- `storage.parquet_metadata`
- `storage.partition_skew`
- `text.near_duplicates`
- `geo.coordinate_validity`
- `nested.schema_paths`

Lenses should be callable directly, recommended automatically, and composable in
reports.

```python
profile.lens("time").cadence(column="event_ts")
profile.lens("concentration").pareto(value="revenue", by="customer_id")
profile.lens("quality").missingness()
```

### 6. Iteration

Running a lens should enrich the profile and update recommendations.

Example:

```python
profile = sf.profile(df, mode="quick")

recs = profile.recommendations()
profile = recs["time.cadence"].run()

profile.recommendations()
```

If cadence analysis finds weekly seasonality, `stateframe` may recommend seasonal
subseries plots. If it finds large time gaps, it may recommend missingness by
time or data freshness checks. If it finds multiple entities observed over time,
it may recommend panel completeness analysis.

This is how `stateframe` gets from a simple first look to highly complex EDA
without overwhelming the user on step one.

## Specialized First Questions By Data Shape

The first profile should route different datasets toward different follow-up
questions.

| Shape | First questions | Recommended lenses |
| --- | --- | --- |
| Time series | Is the cadence regular? Are there gaps, duplicates, seasonality, trend, change points, or timezone anomalies? | `time.cadence`, `time.gaps`, `time.seasonality`, `time.acf`, `time.change_points` |
| Event log | What is one row? Which columns are entities, events, and timestamps? Are there duplicate events or impossible orderings? | `grain.events`, `time.interarrival`, `entity.activity`, `quality.duplicates` |
| Panel data | Are all entity-period combinations present? Are gaps structured by entity? Do entities enter or leave over time? | `panel.completeness`, `panel.balance`, `time.entity_gaps`, `drift.by_period` |
| Transaction table | Who or what drives the totals? Are amounts heavy-tailed? Are there refunds, negative amounts, spikes, or repeated transactions? | `concentration.pareto`, `distribution.heavy_tail`, `grain.transaction_duplicates`, `entity.value` |
| Feature matrix | Which features are constant, redundant, leaky, sparse, high-cardinality, or highly correlated? | `features.readiness`, `relationships.redundancy`, `target.leakage`, `quality.sparsity` |
| Targeted modeling table | Is the target imbalanced? Which variables separate the target? Are any columns suspiciously predictive? | `target.balance`, `target.associations`, `target.leakage`, `drift.train_test` |
| Survey table | Are missing values caused by skip logic? Are response codes consistent? Are low-base questions being overinterpreted? | `survey.skip_patterns`, `categorical.codes`, `missingness.blocks`, `quality.low_base` |
| Text corpus | What languages, lengths, duplicates, near-duplicates, encodings, and token patterns exist? | `text.lengths`, `text.language`, `text.near_duplicates`, `text.tokens` |
| Geospatial points | Are coordinates valid? Are lat/lon swapped? Where are spatial outliers and clusters? | `geo.validity`, `geo.bounds`, `geo.outliers`, `geo.clusters` |
| Nested records | What paths exist? Which keys are optional? Are array lengths stable? Is flattening or exploding needed? | `nested.schema_paths`, `nested.array_lengths`, `nested.type_drift`, `nested.flattening` |
| Parquet dataset | Are schemas consistent? Are files and row groups well-sized? Are partitions skewed? Are statistics useful? | `storage.parquet_metadata`, `storage.schema_drift`, `storage.partition_skew`, `storage.predicate_pushdown` |
| Graph edge list | What is the degree distribution? Are there isolated nodes, self-loops, duplicate edges, or components? | `graph.degree`, `graph.components`, `graph.duplicates`, `graph.self_loops` |

The library should not force the user to pick this shape up front. It should
infer likely shapes and expose them:

```python
profile.shapes()
```

Possible output:

```text
event_log       0.86
panel           0.61
parquet_dataset 1.00
transaction     0.54
```

## Semantic Type Routing

Column semantic types should also trigger different EDA.

Examples:

- Identifier-like columns should get uniqueness, grain, duplicates, joinability,
  and leakage checks.
- Timestamp columns should get range, timezone, granularity, cadence,
  seasonality, and freshness checks.
- Currency and amount columns should get sign analysis, zero inflation,
  heavy-tail checks, concentration, and rounding/heaping analysis.
- Percentage and rate columns should get bounds checks and denominator-risk
  warnings.
- Probability columns should get calibration-style distribution checks and
  impossible-value checks.
- Residual columns should get centeredness, heteroscedasticity, and outlier
  diagnostics.
- Postal codes, countries, states, and cities should get code validity and
  geographic consistency checks.
- Free-text columns should get length, language, encoding, token, duplicate, and
  privacy-risk checks.
- JSON-like columns should get schema-path inference before ordinary string
  analysis.

Semantic inference should always be confidence-scored. A column can have more
than one hypothesis.

```python
profile.column("customer_id").semantic_types()
```

Possible output:

```text
identifier       0.94
foreign_key      0.72
high_cardinality 0.91
```

## Recommendation Object

Recommendations should be first-class objects, not just strings in a report.

Proposed fields:

```python
Recommendation(
    id="time.cadence.event_ts",
    title="Investigate event timestamp cadence",
    lens="time.cadence",
    priority="high",
    score=0.91,
    confidence=0.87,
    cost="low",
    mode="exact",
    columns=["event_ts"],
    requires=["datetime.summary"],
    evidence=[
        "event_ts is the highest-confidence timestamp.",
        "Rows look event-like rather than snapshot-like.",
        "Timestamp spacing appears irregular in the sample."
    ],
    why_it_matters=(
        "Irregular cadence can create misleading trends, biased samples, "
        "and incorrect rolling metrics."
    ),
    produces=[
        "cadence_summary",
        "gap_table",
        "duplicate_timestamp_count",
        "time_gap_plot"
    ],
    code='profile.run("time.cadence", column="event_ts")'
)
```

Recommendation methods:

```python
recs = profile.recommendations()

recs.top(10)
recs.by_category("quality")
recs.by_cost(max_cost="medium")
recs.for_goal("modeling")
recs.to_markdown()
recs[0].run()
```

## Ranking Recommendations

Recommendation ranking should be transparent.

Possible scoring model:

```text
score =
  expected_value
  * confidence
  * relevance_to_goal
  * urgency
  * novelty
  / cost_penalty
```

Where:

- `expected_value` estimates how useful the result is likely to be.
- `confidence` measures how strongly the evidence supports the recommendation.
- `relevance_to_goal` changes when the user says `goal="modeling"`,
  `goal="quality"`, `goal="parquet-audit"`, or `goal="reporting"`.
- `urgency` increases for correctness, leakage, validity, and trust risks.
- `novelty` reduces repeated or already-answered suggestions.
- `cost_penalty` accounts for scan time, memory, dependencies, and user budget.

Costs should be simple at first:

- `metadata-only`
- `cheap`
- `low`
- `medium`
- `high`
- `expensive`

The engine should support budgets:

```python
profile.recommendations(max_cost="medium")
profile.run_recommended(max_cost="low", limit=5)
profile.enrich(budget="2min")
```

## Goals Change The Next Best Lens

The same dataset can deserve different next steps depending on intent.

Supported goals:

- `first-look`: broad, low-noise, highest confidence.
- `quality`: validity, missingness, contracts, anomalies.
- `modeling`: target, leakage, feature readiness, drift, imbalance.
- `time-series`: cadence, gaps, seasonality, autocorrelation, change points.
- `parquet-audit`: files, schemas, row groups, partitions, compression.
- `debug`: suspicious values, duplicates, type coercion, row examples.
- `reporting`: explainable summaries and presentation-ready plots.
- `deep-eda`: advanced diagnostics and exploratory branches.

Example:

```python
profile = sf.profile(df, target="churned", goal="modeling")
profile.recommendations()
```

With a target, the engine should elevate class balance, leakage, feature-target
associations, train/test drift, and proxy-variable warnings.

Without a target, it should emphasize data shape, quality, concentration,
missingness, type inference, and relationship discovery.

## Autonomy Levels

Users should control how active the library is.

```python
sf.profile(df, autonomy="recommend")
sf.profile(df, autonomy="auto-cheap")
sf.profile(df, autonomy="confirm")
sf.profile(df, autonomy="budgeted", budget="5min")
```

Suggested meanings:

- `recommend`: only list next steps.
- `auto-cheap`: automatically run safe, cheap, high-confidence lenses.
- `confirm`: ask before expensive or optional analyses in interactive contexts.
- `budgeted`: run the highest-value lenses within a time or cost budget.

In scripts and CI, there should be no interactive prompts unless explicitly
enabled.

## Python Architecture

Add an agentic layer above the existing profile, metric, issue, and plot design.

Potential package shape:

```text
src/
  stateframe/
    agent/
      __init__.py
      evidence.py
      planner.py
      recommendations.py
      session.py
      scoring.py
      goals.py
      budgets.py
    lenses/
      __init__.py
      registry.py
      base.py
      time.py
      grain.py
      quality.py
      concentration.py
      relationships.py
      storage.py
      target.py
      text.py
      geo.py
      nested.py
      graph.py
    profile.py
    issues.py
    metrics/
    plots/
    backends/
```

This keeps boundaries clean:

- Metrics compute facts.
- Issues interpret facts as risks.
- Lenses run focused diagnostics.
- The planner recommends lenses.
- Sessions coordinate iterative exploration.
- Reports present the story.

## Concrete Python Primitives

The agentic layer can be built with ordinary Python objects. It does not need a
large framework.

Use lightweight dataclasses for the core model:

```python
from dataclasses import dataclass, field
from typing import Any, Literal

ExactnessMode = Literal["exact", "approximate", "sampled", "metadata", "inferred"]
Cost = Literal["metadata-only", "cheap", "low", "medium", "high", "expensive"]


@dataclass(frozen=True)
class EvidenceFact:
    id: str
    subject: str
    value: Any
    mode: ExactnessMode
    method: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ShapeHypothesis:
    id: str
    confidence: float
    evidence_ids: list[str]
    recommended_lenses: list[str]


@dataclass(frozen=True)
class Recommendation:
    id: str
    title: str
    lens: str
    score: float
    confidence: float
    cost: Cost
    columns: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    code: str = ""
```

The `Profile` object can then hold a few stores:

```python
@dataclass
class Profile:
    facts: dict[str, EvidenceFact]
    shapes: dict[str, ShapeHypothesis]
    issues: list[Issue]
    lens_results: dict[str, LensResult]
    recommendation_history: list[str]
    context: UserContext

    def recommendations(self, **filters):
        return Planner.default().plan(self, **filters)

    def run(self, lens_id: str, **params):
        result = LensRegistry.default().run(lens_id, self, **params)
        return self.with_lens_result(result)
```

The planner is just a pipeline:

```python
class Planner:
    def plan(self, profile, goal=None, max_cost=None, limit=None):
        candidates = []

        for rule in RecommendationRuleRegistry.default():
            candidates.extend(rule.apply(profile))

        candidates = self.dedupe(candidates)
        candidates = self.score(candidates, profile, goal=goal)
        candidates = self.filter_by_cost(candidates, max_cost=max_cost)
        candidates = self.remove_completed(candidates, profile)

        return RecommendationList(candidates[:limit])
```

This is deliberately plain. The magic should live in the quality of the facts,
lenses, rules, and explanations, not in a complicated orchestration system.

## Evidence Model

The recommendation engine should work from structured evidence.

Core evidence types:

- `MetricFact`: measured statistic.
- `MetadataFact`: file, schema, partition, or backend fact.
- `SemanticTypeHypothesis`: inferred column meaning.
- `DatasetShapeHypothesis`: inferred table shape.
- `Issue`: ranked risk or warning.
- `LensResult`: output from a deeper diagnostic.
- `UserContext`: target, time column, entity column, goal, budget, mode.

All evidence should preserve provenance:

- Method.
- Backend.
- Parameters.
- Sample size.
- Exactness mode.
- Timestamp.
- Confidence.

Example:

```python
MetricFact(
    id="column.null_ratio",
    subject="email",
    value=0.42,
    mode="exact",
    method="pandas.isna.mean",
    confidence=1.0
)
```

This makes recommendations auditable:

```python
rec = profile.recommendations()[0]
rec.evidence
rec.explain()
```

## Lens Registry

Every lens should declare when it applies, what it needs, what it costs, and
what it produces.

Sketch:

```python
@lens(
    id="time.cadence",
    title="Time cadence analysis",
    applies_to=["datetime"],
    shapes=["time_series", "event_log", "panel"],
    cost="low",
    produces=["cadence_summary", "gap_table", "cadence_plot"],
)
def time_cadence(profile, column=None, groupby=None):
    ...
```

Registry metadata:

- Lens id and aliases.
- Compatible semantic types.
- Compatible dataset shapes.
- Required metrics or columns.
- Optional parameters.
- Cost estimate.
- Backend support.
- Exact, approximate, sampled, or metadata-only support.
- Recommendation rules.
- Plot specs produced.
- Issue rules produced.

This registry turns a giant EDA catalog into discoverable building blocks.

## Rule-Based Recommendation Engine

The first engine should be rule-based and data-driven.

Example rules:

```python
if has_shape("time_series", min_confidence=0.65):
    recommend("time.cadence")
    recommend("time.gaps")

if has_semantic_type(column, "identifier") and duplicate_ratio(column) > 0:
    recommend("grain.duplicate_keys", column=column)

if is_positive_numeric(column) and top_share(column, q=0.01) > 0.5:
    recommend("concentration.lorenz", column=column)

if is_parquet_dataset() and file_size_cv() > 1.5:
    recommend("storage.file_skew")

if target and association_score(column, target) > 0.98:
    recommend("target.leakage", column=column)
```

Rules should be stored in a registry, not scattered through report code.

Later, the engine can add learned priors:

- Which recommendations users often run after certain profiles.
- Which lenses tend to produce high-severity issues for certain shapes.
- Which expensive analyses are rarely useful for small or clean datasets.

But deterministic rules should carry the product through the MVP.

## Query Planning And Performance

Agentic EDA only works if the initial profile is fast enough to trust.

Python implementation strategy:

- Use backend adapters for pandas, Polars, PyArrow, DuckDB, and Parquet metadata.
- Compile requested metrics into the fewest practical passes over the data.
- Use metadata-only answers when they are good enough.
- Use sketches for approximate distinct counts and heavy hitters on large data.
- Use samples when full scans are too expensive, and label results clearly.
- Cache metric results inside the profile.
- Let lenses declare dependencies so running a lens reuses existing facts.
- Push projection and predicates into Polars, DuckDB, or Arrow when possible.

Example:

```python
profile = sf.profile(
    "events/*.parquet",
    mode="quick",
    engine="duckdb",
    sample=100_000,
)

profile.recommendations(max_cost="low")
```

The planner should avoid recommending expensive relationship scans across 500
columns unless the user requested `deep-eda` or `modeling`.

## Profile As A Living Artifact

The profile should be append-only in spirit. A deeper lens enriches it rather
than replacing it.

```python
profile = sf.profile(df, mode="quick")
profile = profile.enrich("quality")
profile = profile.enrich("time")
profile = profile.enrich("relationships", max_cost="medium")
```

The profile stores:

- Initial evidence.
- Lens results.
- Recommendations that were accepted, skipped, or completed.
- Runtime and cost.
- User-provided context.
- Exportable JSON.

This enables:

- Reproducible EDA sessions.
- Report regeneration.
- Profile diffs.
- CI checks.
- Future "continue where I left off" workflows.

## User Experience

The default report should answer:

1. What kind of dataset does this appear to be?
2. What should I worry about first?
3. What is interesting?
4. What should I run next?
5. What can be turned into a reusable check?

Example terminal output:

```text
stateframe profile: 2.4M rows x 38 columns

Likely shapes
  parquet_dataset  1.00
  event_log        0.86
  transaction      0.62

Top issues
  warning  event_ts has 14 large time gaps
  warning  revenue is highly concentrated
  info     customer_id looks like a non-unique entity key

Recommended next lenses
  1. time.cadence(event_ts)                 low
  2. concentration.pareto(revenue, customer_id) medium
  3. storage.partition_skew()               metadata-only
```

The key is that recommendations are not generic. They are tied to this dataset.

## Report Design For Agentic EDA

Agentic reports should include a "Next Best EDA" section near the top.

Recommended report sections:

- Executive summary.
- Inferred dataset shapes.
- Top issues.
- Next best EDA recommendations.
- Evidence behind recommendations.
- Completed lenses and findings.
- Suggested checks.
- Appendix of metrics and methods.

Each recommendation in the report should include:

- One-sentence reason.
- Code to run it.
- Expected output.
- Cost.
- Confidence.
- Related issues.

This turns a static HTML report into a launchpad for deeper work.

## Suggested Public API

### First Look

```python
profile = sf.profile(df)
profile.summary()
profile.recommendations()
```

### Run Recommended Work

```python
profile.run_recommended(limit=3, max_cost="medium")
```

### Inspect And Run One Recommendation

```python
recs = profile.recommendations()
rec = recs[0]

rec.explain()
profile = rec.run()
```

### Goal-Oriented Exploration

```python
profile = sf.profile(df, goal="modeling", target="churned")
profile.recommendations()
```

### Session Workflow

```python
session = sf.explore(df, goal="quality")

session.summary()
session.next()
session.run_next()
session.history()
session.report("quality-review.html")
```

### Ask For A Lens Directly

```python
profile.run("missingness.blocks")
profile.run("distribution.heavy_tail", column="claim_amount")
profile.run("relationships.mixed_associations", target="churned")
```

## MVP Recommendation Set

The first version does not need hundreds of recommendations. It needs a small
set that feels uncannily useful.

MVP recommendations:

- Mostly missing columns.
- All-null, constant, and near-constant columns.
- Mixed object columns that should be numeric, datetime, boolean, JSON, or
  category.
- Identifier-like columns and duplicate key risks.
- Candidate row grain.
- Datetime cadence, gaps, duplicate timestamps, and timezone issues.
- High-cardinality categorical columns.
- Rare-category and category concentration checks.
- Positive numeric concentration using Lorenz or Pareto.
- Numeric heavy tails, zero inflation, and outlier concentration.
- Missingness block and co-occurrence analysis.
- Basic relationship scan when column count is reasonable.
- Target balance and leakage when a target is provided.
- Parquet schema drift, file skew, row-group skew, and partition skew.
- Suggested Pandera-style checks from high-confidence facts.

This set would already make `stateframe` feel meaningfully smarter than a static
profiler.

## Implementation Phases

### Phase 1: Evidence And Recommendations

- Add structured evidence objects.
- Add recommendation objects.
- Add rule-based planner.
- Add `profile.recommendations()`.
- Add recommendations from existing profile facts.
- Render recommendations in terminal, Markdown, HTML, and JSON.

### Phase 2: Shape Inference

- Add dataset shape hypotheses.
- Add semantic type confidence scores.
- Add `profile.shapes()`.
- Add shape-triggered recommendations.

### Phase 3: Lens Registry

- Add lens metadata.
- Add `profile.run(lens_id, **params)`.
- Add dependency tracking.
- Add cached lens results.

### Phase 4: Guided Sessions

- Add `sf.explore()`.
- Track completed, skipped, and pending recommendations.
- Add `session.next()` and `session.run_next()`.
- Add budgeted execution.

### Phase 5: Advanced And Optional Intelligence

- Add goal-specific planners.
- Add learned recommendation priors from local anonymous-free usage history only
  if the user opts in.
- Add optional LLM narration without exposing raw data by default.
- Add natural-language goal parsing.

## What To Avoid

- Do not call it agentic if it only generates a longer static report.
- Do not hide why a recommendation was made.
- Do not run expensive scans without clear user intent or a budget.
- Do not imply causality from exploratory associations.
- Do not bury recommendations after hundreds of metrics.
- Do not make an LLM mandatory.
- Do not send data to a server.
- Do not recommend advanced statistics just because they exist.

## Why This Can Be Best-In-Class

The best EDA library will not be the one with the longest checklist of metrics.
It will be the one that helps users move from unknown data to the right next
question fastest.

`stateframe` can win by combining:

- A simple one-line start.
- A reusable profile object.
- Parquet-native metadata intelligence.
- Shape and semantic type inference.
- A registry of powerful EDA lenses.
- A transparent recommendation engine.
- Budget-aware execution.
- Reports that explain what to do next.
- Suggested checks that turn exploration into practice.

The guiding promise:

> `stateframe` does not just show you your data. It helps you decide where to look
> next.
