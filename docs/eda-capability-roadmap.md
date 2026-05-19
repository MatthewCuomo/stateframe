# stateframe EDA Capability Roadmap

This document is the working inventory for what `stateframe` could eventually make easy.
The north star is simple: give a data scientist a lens on the real shape of a
dataset before they clean, model, report, or trust it.

The library should not only compute ordinary summary statistics. It should expose
basic, advanced, and rarely used but powerful EDA ideas through one coherent API.
This file is intentionally broad. Later we can split it into an MVP, advanced
modules, and plugin candidates.

## Product Principles

- Be useful on the first line of code.
- Work with both in-memory DataFrames and Parquet datasets.
- Prefer actionable findings over metric dumps.
- Make advanced statistics discoverable without requiring the user to remember
  every test, plot, or diagnostic by name.
- Support fast approximate scans before exact expensive scans.
- Preserve reproducibility: every metric, plot, sample, warning, and inference
  should have a method, parameters, backend, and timestamp.
- Keep outputs composable: summary tables, plot specs, issue lists, contracts,
  JSON, Markdown, HTML, and notebooks should all come from the same profile.
- Treat EDA as layered: storage shape, schema shape, statistical shape, semantic
  shape, relationship shape, time shape, quality shape, and model-readiness shape.

## Capability Tiers

- Tier 0: Basic, expected in any EDA package.
- Tier 1: Strong differentiators that serious data scientists use often.
- Tier 2: Advanced diagnostics that are powerful but less commonly packaged well.
- Tier 3: Research-grade or specialized methods that should be opt-in.

## Dataset Intake And Storage Shape

### Dataset Discovery

- Detect file type: CSV, TSV, JSONL, JSON, Parquet, Feather, IPC, ORC, Excel.
- Detect single file vs directory dataset.
- Detect Hive-style partition columns.
- Detect glob expansion results.
- Detect hidden/system files and malformed files in a dataset directory.
- Detect mixed file formats in one input.
- Detect file encodings for text files.
- Detect delimiter, quote, escape, comment, header, and line-ending style.
- Detect compressed inputs: gzip, bz2, zip, xz, zstd, snappy where applicable.
- Detect remote sources later: S3, GCS, Azure Blob, HTTPS.
- Detect whether data can be scanned lazily.
- Estimate full dataset size before loading.
- Estimate row count before loading where metadata permits.
- Estimate memory needed to materialize data.
- Recommend loading engine: pandas, Polars, PyArrow, DuckDB.

### Parquet-Specific Shape

- File count.
- Total bytes.
- Total rows from metadata.
- Row groups per file.
- Rows per row group.
- Row group size distribution.
- Column chunk size distribution.
- Compression codec per column.
- Encoding per column.
- Dictionary encoding usage.
- Bloom filter availability where exposed.
- Min, max, null count, and distinct count statistics from metadata where present.
- Missing or incomplete statistics detection.
- Schema by file.
- Schema drift across files.
- Logical type drift across files.
- Physical type drift across files.
- Column order drift.
- Partition column consistency.
- Partition value cardinality.
- Partition skew.
- File size skew.
- Row count skew.
- Row group skew.
- Small files problem detection.
- Oversized files detection.
- Compression effectiveness by column.
- High-cardinality columns without dictionary benefit.
- Sortedness hints from row-group min/max monotonicity.
- Predicate pushdown usefulness score.
- Columns that are expensive to scan relative to usefulness.
- Columns that dominate storage.
- Candidate columns for partitioning.
- Candidate columns for sorting or clustering.
- Candidate columns for dictionary encoding.
- Candidate row group sizing recommendations.
- Cross-file duplicate schema fingerprints.
- Corrupt or unreadable file detection.
- Parquet metadata report without reading all rows.

### DataFrame Intake

- Detect DataFrame engine: pandas, Polars, PyArrow Table, DuckDB relation,
  Dask, Spark DataFrame later.
- Detect index information for pandas.
- Detect lazy vs eager state.
- Detect nullable vs non-nullable dtypes.
- Detect extension dtypes.
- Detect timezone-aware datetime columns.
- Detect categorical columns.
- Detect nested/list/struct columns.
- Detect object columns with mixed Python types.
- Detect object columns that should be numeric, boolean, datetime, category, JSON,
  list, or struct.
- Detect duplicate column names.
- Detect invalid or surprising column names.
- Detect columns that are all null, constant, or nearly constant.
- Detect rows that are all null or nearly empty.

## Sampling Strategy

### Sampling Methods

- Head, tail, random, and stratified samples.
- Reservoir sampling for streaming data.
- Bernoulli sampling.
- Systematic sampling.
- Weighted sampling.
- Cluster sampling.
- Group-preserving sampling.
- Time-window sampling.
- Rare-category-preserving sampling.
- Outlier-preserving sampling.
- Quantile sketch sampling.
- Partition-balanced sampling.
- Row-group-balanced Parquet sampling.
- Sample enough rows to stabilize a metric.
- Confidence intervals around sampled metrics.
- Warnings when sample-based findings are unstable.

### Sampling Diagnostics

- Compare sample profile to full metadata profile.
- Compare sample column distributions to metadata min/max.
- Detect sample bias across partitions.
- Detect sample bias across groups.
- Effective sample size.
- Coverage of rare categories.
- Coverage of missingness patterns.
- Coverage of date ranges.
- Coverage of numeric tails.

## Dataset-Level Summary

### Core Dimensions

- Row count.
- Column count.
- Memory usage.
- Disk usage.
- Estimated compressed vs uncompressed size.
- Duplicate row count.
- Duplicate row ratio.
- Complete row count.
- Complete row ratio.
- Empty row count.
- Empty row ratio.
- Missing cell count.
- Missing cell ratio.
- Dense vs sparse shape.
- Wide vs tall classification.
- Column type counts.
- Numeric/categorical/datetime/text/boolean/geospatial/nested mix.
- Average non-null values per row.
- Average non-null values per column.
- Dataset entropy summary.
- Dataset compressibility summary.
- Cardinality profile.
- Row uniqueness profile.
- Candidate grain summary.

### Dataset Shape Descriptors

- Tall-narrow, wide-short, sparse-wide, dense-wide, panel, event log, snapshot,
  slowly changing dimension, transaction table, time series, matrix, graph edge
  list, survey table, feature matrix.
- Data maturity classification: raw extract, normalized analytic table, feature
  table, aggregated table, report output, model output.
- Row grain inference.
- Entity column inference.
- Event timestamp inference.
- Measure vs dimension column inference.
- Potential target column inference.
- Potential leakage column inference.

## Column-Level Basics

### Universal Column Metrics

- dtype and inferred semantic type.
- Non-null count.
- Null count.
- Null ratio.
- Distinct count.
- Distinct ratio.
- Unique count.
- Unique ratio.
- Constant or near-constant flag.
- Mode.
- Mode frequency.
- Mode ratio.
- Top values.
- Bottom values where ordered.
- Example values.
- Invalid values according to inferred type.
- Approximate distinct count for large data.
- Entropy.
- Normalized entropy.
- Gini impurity for categorical-like columns.
- Simpson diversity index.
- Herfindahl-Hirschman index.
- Effective number of categories.
- Compression ratio proxy.
- Value length stats for string-like columns.
- Token count stats for text-like columns.
- Character class profile.
- Whitespace profile.
- Case profile.
- Leading/trailing whitespace count.
- Empty string count.
- Placeholder null count: `NA`, `N/A`, `null`, `None`, `?`, `-`, empty string.
- Parse success rates into numeric, datetime, boolean, JSON.

### Numeric Basic Metrics

- Count.
- Mean.
- Median.
- Minimum.
- Maximum.
- Range.
- Variance.
- Standard deviation.
- Standard error.
- Coefficient of variation.
- Sum.
- Product where meaningful.
- Quantiles: p1, p5, p10, p25, p50, p75, p90, p95, p99.
- Interquartile range.
- Median absolute deviation.
- Mean absolute deviation.
- Root mean square.
- Trimmed mean.
- Winsorized mean.
- Geometric mean for positive data.
- Harmonic mean for positive data.
- Midrange.
- Midhinge.
- Trimean.
- Five-number summary.
- Seven-number summary.
- Tukey fences.
- Percent below zero, equal zero, above zero.
- Percent integer-valued.
- Percent finite, infinite, NaN.

### Numeric Shape Metrics

- Skewness.
- Robust skewness.
- Bowley skewness.
- Medcouple robust skewness.
- Kurtosis.
- Excess kurtosis.
- Robust kurtosis.
- Tail weight.
- Tail ratio.
- Left-tail and right-tail mass.
- Asymmetry score.
- Modality hints.
- Number of local modes.
- Peak count from kernel density estimate.
- Quantile spacing ratios.
- Spread stability across quantile bands.
- Outlier counts by IQR.
- Outlier counts by z-score.
- Outlier counts by modified z-score.
- Outlier counts by robust Mahalanobis in multivariate context.
- Extreme value index.
- Hill estimator for heavy-tail behavior.
- Zero inflation score.
- Spike score.
- Heaping score.
- Round-number preference.
- Digit preference.
- Benford conformity for naturally occurring positive measures.
- Log-normality hints.
- Power-law hints.
- Boundedness inference.

### Categorical Basic Metrics

- Distinct categories.
- Top-k frequencies.
- Rare category count.
- Rare category ratio.
- Long-tail category count.
- Category entropy.
- Category concentration.
- Category balance.
- Category imbalance ratio.
- Category coverage needed for 80/90/95/99 percent of rows.
- Effective category count.
- Missing category pattern.
- Categories with leading/trailing whitespace.
- Case-variant duplicates.
- Unicode normalization duplicates.
- Punctuation-variant duplicates.
- Fuzzy duplicate category suggestions.
- Category value length distribution.
- Category frequency table.

### Boolean Metrics

- True count.
- False count.
- Missing count.
- True ratio.
- False ratio.
- Imbalance ratio.
- Values outside true/false set.
- Boolean encoded as string or numeric detection.
- Mostly boolean detection.

### Datetime Metrics

- Minimum timestamp.
- Maximum timestamp.
- Time span.
- Timezone awareness.
- Timezone mix.
- Date parse failure rate.
- Granularity: date, hour, minute, second, millisecond, microsecond.
- Timestamp precision actually used.
- Frequency inference.
- Gaps in expected frequency.
- Duplicate timestamps.
- Monotonicity.
- Seasonality hints.
- Weekday distribution.
- Hour-of-day distribution.
- Day-of-month distribution.
- Month distribution.
- Quarter distribution.
- Business-day vs calendar-day behavior.
- Holiday proximity later.
- Daylight-saving anomalies.
- Future dates.
- Implausible old dates.
- Sentinel dates such as 1900-01-01, 1970-01-01, 9999-12-31.

### Text Metrics

- Character count distribution.
- Word count distribution.
- Sentence count distribution.
- Token count distribution.
- Unique token count.
- Vocabulary size.
- Lexical diversity.
- Type-token ratio.
- Stopword ratio.
- Numeric token ratio.
- Punctuation ratio.
- Uppercase ratio.
- URL count.
- Email count.
- Phone-like count.
- Hashtag/mention count.
- Language detection.
- Encoding artifacts.
- Non-ASCII character profile.
- Emoji count if relevant.
- Duplicate text count.
- Near-duplicate text clusters.
- MinHash signatures.
- SimHash signatures.
- N-gram frequency.
- TF-IDF top terms.
- Topic hints later.
- Sentiment hints optional, clearly marked as model-dependent.

### Geospatial Metrics

- Latitude/longitude detection.
- Coordinate validity.
- Bounding box.
- Centroid.
- Convex hull.
- Point density.
- Spatial outliers.
- Geohash distribution.
- Coordinate precision.
- Repeated coordinate count.
- Impossible coordinates.
- Swapped latitude/longitude detection.
- Distance-to-centroid distribution.
- Cluster hints.
- Projection/CRS detection later for GeoDataFrames.

### Nested And Semi-Structured Metrics

- JSON parse success rate.
- Object key frequencies.
- Nested schema inference.
- Optional vs required keys.
- Array length distribution.
- Struct field null rates.
- Field type drift.
- Deep missingness.
- Flattening recommendations.
- Explode recommendations.
- Repeated substructure detection.
- Path-level cardinality.

## Distribution Plots

### Core Numeric Distribution Plots

- Histogram.
- Density plot.
- Kernel density estimate.
- Rug plot.
- Box plot.
- Violin plot.
- Strip plot.
- Swarm plot.
- Beeswarm plot.
- Raincloud plot.
- Dot plot.
- Quantile dot plot.
- ECDF plot.
- Complementary CDF plot.
- Survival curve for nonnegative values.
- Percentile plot.
- Quantile function plot.
- Stem-and-leaf display.
- Letter-value plot for large data.
- Boxen plot.
- Ridgeline plot for grouped distributions.
- Joy plot for grouped distributions.
- Frequency polygon.
- Average shifted histogram.

### Advanced Distribution Diagnostics

- Q-Q plot against normal.
- Q-Q plot against lognormal.
- Q-Q plot against exponential.
- Q-Q plot against gamma.
- Q-Q plot against beta.
- Q-Q plot against t distribution.
- P-P plot.
- Probability plot.
- Detrended Q-Q plot.
- Worm plot.
- Tukey mean-difference plot.
- Spread-location plot.
- Scale-location plot.
- Mean excess plot for tail behavior.
- Hill plot for heavy-tail index.
- Zipf plot for rank-frequency data.
- Log-log rank-size plot.
- Probability integral transform histogram.
- Residual distribution plot for transformations.
- Cullen-Frey skewness-kurtosis plot.
- Cullen-Frey bootstrap cloud.

### Concentration And Inequality Plots

- Lorenz curve.
- Generalized Lorenz curve.
- Concentration curve.
- Cumulative concentration curve by sorted contribution.
- Pareto chart.
- ABC analysis curve.
- Cumulative share plot.
- Cumulative top-k contribution curve.
- Decile contribution plot.
- Percentile contribution plot.
- Share of total held by top 1/5/10 percent.
- Gini coefficient visualization.
- Theil index decomposition plot.
- Atkinson index sensitivity plot.
- Herfindahl contribution plot.
- Dominance curve.
- Lift curve.
- Cumulative gains chart.
- Capture curve for target concentration.
- Rare-category cumulative coverage curve.

### Distribution Comparison Plots

- Overlayed histograms.
- Overlayed KDEs.
- Side-by-side box plots.
- Side-by-side violin plots.
- Ridgeline by group.
- ECDF comparison.
- Q-Q plot between two samples.
- Shift function plot.
- Quantile difference plot.
- Percentile ratio plot.
- Bland-Altman plot.
- Gardner-Altman estimation plot.
- Pirate plot.
- Distribution heatmap by group.
- Beeswarm plus interval summary.
- Raincloud by group.
- Violin with embedded box and points.

## Categorical Plots

- Bar chart.
- Ordered frequency bar chart.
- Pareto bar chart.
- Lollipop chart.
- Cleveland dot plot.
- Treemap for category share.
- Mosaic plot.
- Spine plot.
- Waffle chart.
- Packed bubble chart optional.
- Word cloud optional and de-emphasized.
- Category frequency table with cumulative share.
- Rare-category rollup plot.
- Category entropy visual.
- Category imbalance plot.
- Category drift bar chart.
- Category emergence/disappearance plot.
- Category co-occurrence network.
- UpSet plot for set-like categorical combinations.
- Alluvial plot for categorical flows.
- Sankey plot for transitions.
- Chord diagram later for category relationships.

## Missingness Analysis

### Missingness Metrics

- Missing count by column.
- Missing ratio by column.
- Missing count by row.
- Missing ratio by row.
- Complete case count.
- Complete case ratio.
- Missingness entropy.
- Missingness concentration.
- Missingness co-occurrence.
- Missingness correlation.
- Missingness clusters.
- Monotone missingness pattern detection.
- Block missingness detection.
- Structured missingness by group.
- Missingness by time.
- Missingness by partition/file.
- Missingness by row order.
- Missingness associated with target.
- Missingness associated with other features.
- Missing completely at random heuristics.
- Missing at random heuristics.
- Missing not at random hints, carefully worded.
- Placeholder null detection.

### Missingness Plots

- Missingness bar chart.
- Missingness matrix.
- Missingness heatmap.
- Missingness dendrogram.
- Missingness upset plot.
- Missingness co-occurrence network.
- Row completeness histogram.
- Column completeness histogram.
- Missingness by time plot.
- Missingness by group plot.
- Missingness by file or partition plot.
- Nullity sparkline.
- Missingness run-length plot.
- Missingness block map.

## Relationship Analysis

### Pairwise Numeric Relationships

- Pearson correlation.
- Spearman correlation.
- Kendall correlation.
- Biweight midcorrelation.
- Distance correlation.
- MIC / maximal information coefficient optional.
- Hoeffding's D.
- Chatterjee correlation.
- Mutual information.
- Partial correlation.
- Semi-partial correlation.
- Robust correlation.
- Correlation confidence intervals.
- Correlation p-values with multiple-testing caution.
- Correlation stability under sampling.
- Correlation by group.
- Correlation drift over time.
- Nonlinear association score.

### Numeric Relationship Plots

- Scatter plot.
- Hexbin plot.
- 2D histogram.
- Contour density plot.
- KDE contour plot.
- Datashaded scatter for large data.
- Scatter with marginal histograms.
- Scatter with marginal densities.
- Scatter with quantile regression lines.
- Scatter with LOESS smoother.
- Scatter with robust smoother.
- Binned scatter plot.
- Residualized scatter plot.
- Bubble plot.
- Connected scatter for ordered observations.
- Pair plot.
- Scatterplot matrix.
- Correlation heatmap.
- Clustered correlation heatmap.
- Correlogram.
- Partial correlation network.
- Graphical lasso network optional.

### Numeric-Categorical Relationships

- Grouped summary stats.
- Difference in means.
- Difference in medians.
- Effect size: Cohen's d.
- Effect size: Hedges' g.
- Effect size: Glass delta.
- Effect size: Cliff's delta.
- Common language effect size.
- Eta squared.
- Omega squared.
- Epsilon squared.
- ANOVA.
- Welch ANOVA.
- Kruskal-Wallis.
- Mann-Whitney U.
- Brunner-Munzel.
- Mood median test.
- Levene variance test.
- Brown-Forsythe test.
- Fligner-Killeen test.
- Group distribution overlap.
- Group separation score.
- Target leakage warning for perfectly separating features.
- Grouped box/violin/raincloud plots.
- Mean and confidence interval plots.
- Median and bootstrap interval plots.
- Gardner-Altman group comparison.
- Shift function by group.
- Ridgeline by category.

### Categorical-Categorical Relationships

- Contingency table.
- Crosstab with row percentages.
- Crosstab with column percentages.
- Expected counts.
- Chi-square test.
- Fisher exact test for 2x2.
- G-test / likelihood-ratio chi-square.
- Cramer's V.
- Tschuprow's T.
- Theil's U.
- Uncertainty coefficient.
- Mutual information.
- Adjusted mutual information.
- Phi coefficient.
- Odds ratio.
- Relative risk.
- Risk difference.
- Standardized residuals.
- Association heatmap.
- Mosaic plot.
- Sieve plot.
- Spine plot.
- Balloon plot.
- Residual association plot.
- Correspondence analysis plot.

### Datetime Relationships

- Value over time.
- Aggregation over time.
- Rolling mean.
- Rolling median.
- Rolling quantiles.
- Rolling standard deviation.
- Rolling missingness.
- Rolling distinct count.
- Seasonal subseries plot.
- Calendar heatmap.
- Hour-week heatmap.
- Month-year heatmap.
- Lag plot.
- Autocorrelation plot.
- Partial autocorrelation plot.
- Cross-correlation plot.
- Change-point hints.
- STL decomposition.
- Trend-season-residual view.
- Event burst detection.
- Time since previous event.
- Interarrival time distribution.
- Recency-frequency diagnostics.

## Multivariate Structure

### Multivariate Metrics

- Pairwise completeness matrix.
- Pairwise correlation matrix.
- Pairwise mutual information matrix.
- Covariance matrix.
- Robust covariance matrix.
- Condition number.
- Multicollinearity score.
- Variance inflation factor.
- Effective rank.
- Intrinsic dimensionality estimate.
- Participation ratio.
- Principal component variance explained.
- Singular value profile.
- Matrix sparsity.
- Low-rank approximation error.
- Redundancy clusters.
- Feature grouping by association.
- Feature dominance.
- Feature uniqueness score.
- Multi-column duplicate information.

### Multivariate Plots

- Pair plot.
- Scatterplot matrix.
- Parallel coordinates.
- Andrews curves.
- RadViz.
- PCA scree plot.
- PCA biplot.
- PCA loadings heatmap.
- Cumulative variance explained plot.
- UMAP projection.
- t-SNE projection.
- PHATE projection later.
- TriMap projection later.
- MDS projection.
- Isomap projection later.
- Feature clustering dendrogram.
- Observation clustering dendrogram.
- Cluster heatmap.
- Bicorrelation heatmap.
- Sparse matrix visualization.
- Missingness plus value cluster map.
- Grand tour / projection pursuit later.

### Clustering As EDA

- K-means profile scan.
- Hierarchical clustering.
- HDBSCAN later.
- DBSCAN later.
- Gaussian mixture model later.
- Silhouette score.
- Davies-Bouldin score.
- Calinski-Harabasz score.
- Gap statistic.
- Cluster size balance.
- Cluster stability under resampling.
- Cluster feature summaries.
- Cluster contrast report.
- Cluster outlier scores.
- Cluster representative rows.
- Cluster boundary diagnostics.

## Outliers And Anomalies

### Univariate Outliers

- Z-score.
- Modified z-score.
- IQR fences.
- Adjusted boxplot for skewed distributions.
- Percentile caps.
- Extreme quantile flags.
- Median absolute deviation.
- Hampel filter.
- Grubbs test optional.
- Generalized ESD test optional.
- Peaks-over-threshold diagnostics.
- Tail probability under fitted distribution.

### Multivariate Outliers

- Mahalanobis distance.
- Robust Mahalanobis distance.
- Minimum covariance determinant.
- Isolation Forest optional.
- Local Outlier Factor optional.
- One-class SVM optional.
- Elliptic envelope optional.
- kNN distance outlier score.
- PCA reconstruction error.
- Autoencoder reconstruction error later.
- Angle-based outlier detection later.
- Subspace outlier detection later.
- High-leverage point detection.
- Influence diagnostics when a model is involved.

### Outlier Plots

- Outlier-labeled scatter.
- Robust distance plot.
- Mahalanobis Q-Q plot.
- Influence plot.
- Leverage-residual plot.
- Box plot with adjusted fences.
- Extreme-value tail plot.
- Top anomaly table.
- Outlier contribution waterfall.
- Outlier profile cards.

## Data Quality And Validity

### Rule-Free Quality Hints

- Constant column.
- Near-constant column.
- Duplicate rows.
- Duplicate columns.
- Nearly duplicate columns.
- Conflicting duplicates by key.
- Primary-key candidate violations.
- Foreign-key candidate violations.
- Referential orphan hints.
- Mixed units.
- Mixed currencies.
- Mixed date formats.
- Mixed categorical coding systems.
- Impossible values.
- Implausible values.
- Sentinel values.
- Clipped values.
- Truncated text.
- Rounded values.
- Heaped values.
- Precision loss.
- Numeric overflow hints.
- Type coercion loss.
- Empty strings as data.
- Unexpected whitespace.
- Identifier columns stored as floats.
- Leading-zero loss.
- High missingness.
- High cardinality.
- Rare levels.
- Class imbalance.
- Data leakage hints.
- Target duplicates.
- Train/test contamination hints.

### Rule-Based Checks

- Range checks.
- Set membership checks.
- Regex checks.
- Date bounds.
- Non-null checks.
- Unique checks.
- Composite uniqueness checks.
- Monotonicity checks.
- Cross-column inequalities.
- Sum-to-total checks.
- Ratio bounds.
- Conditional checks.
- Group-level checks.
- Window-level checks.
- Freshness checks.
- Volume checks.
- Schema checks.
- Row count checks.
- Partition completeness checks.
- Contract drift checks.

### Contract Generation

- Suggested Pandera schema.
- Suggested Great Expectations suite.
- Suggested Pydantic model for row-like records.
- Suggested JSON Schema for nested columns.
- Suggested SQL DDL.
- Suggested dbt tests.
- Suggested YAML data contract.
- Confidence score per suggested rule.
- Strict vs tolerant contract modes.
- Baseline profile export.
- Contract diff.

## Semantic Type Inference

### Semantic Column Types

- Identifier.
- Primary key candidate.
- Foreign key candidate.
- Natural key.
- Surrogate key.
- Timestamp.
- Date.
- Duration.
- Currency.
- Percentage.
- Rate.
- Count.
- Quantity.
- Score.
- Rank.
- Latitude.
- Longitude.
- Postal code.
- Country.
- State/province.
- City.
- Email.
- URL.
- Phone.
- IP address.
- UUID.
- Hash.
- JSON.
- Free text.
- Category.
- Ordinal category.
- Binary flag.
- Target variable.
- Prediction output.
- Probability.
- Residual.
- Weight.
- Exposure.
- Sensitive attribute candidate.

### Semantic Inference Signals

- Column name patterns.
- Value regex patterns.
- Cardinality.
- Nullability.
- Value range.
- Numeric distribution.
- String length distribution.
- Prefix/suffix patterns.
- Known code lists optional.
- Correlation with row order.
- Correlation with target.
- File partition context.
- Temporal behavior.
- Uniqueness behavior.
- Format consistency.

## Grain, Keys, And Relational Shape

- Candidate primary keys.
- Candidate composite keys.
- Key uniqueness score.
- Key nullability.
- Key stability over time.
- Duplicate key groups.
- Conflicting values within key groups.
- Entity columns.
- Event columns.
- Snapshot columns.
- Slowly changing dimension hints.
- One-row-per-entity inference.
- One-row-per-event inference.
- One-row-per-entity-period inference.
- One-to-one relationship hints.
- One-to-many relationship hints.
- Many-to-many relationship hints.
- Parent-child hierarchy hints.
- Bridge table hints.
- Fact table vs dimension table hints.
- Star schema hints.
- Joinability score between two datasets.
- Join key suggestions.
- Join explosion risk.
- Join coverage.
- Anti-join summary.
- Referential integrity scan.

## Dataset Comparison And Drift

### Comparison Modes

- Compare two DataFrames.
- Compare two Parquet datasets.
- Compare train vs test.
- Compare baseline vs current.
- Compare month-over-month.
- Compare before vs after cleaning.
- Compare sample vs full.
- Compare schema only.
- Compare metadata only.
- Compare distributions only.
- Compare quality only.

### Drift Metrics

- Schema drift.
- Type drift.
- Column addition/removal.
- Missingness drift.
- Cardinality drift.
- Range drift.
- Quantile drift.
- Mean/median drift.
- Variance drift.
- Skewness/kurtosis drift.
- Category frequency drift.
- New category emergence.
- Category disappearance.
- Population stability index.
- Jensen-Shannon divergence.
- Kullback-Leibler divergence with caution.
- Wasserstein distance.
- Kolmogorov-Smirnov statistic.
- Anderson-Darling k-sample test.
- Energy distance.
- Maximum mean discrepancy later.
- Earth mover distance.
- Hellinger distance.
- Total variation distance.
- Cramer-von Mises statistic.
- Target rate drift.
- Calibration drift.
- Concept drift hints later.

### Drift Plots

- Distribution overlay.
- ECDF overlay.
- Quantile difference plot.
- PSI contribution bars.
- Wasserstein movement plot.
- Category frequency before/after bars.
- New/lost category table.
- Missingness delta heatmap.
- Schema diff tree.
- Metric sparkline over snapshots.
- Drift severity heatmap.
- Top-changing columns report.

## Target-Aware EDA

### Regression Target

- Target distribution.
- Target skew/kurtosis.
- Target outliers.
- Feature-target correlation.
- Feature-target mutual information.
- Feature-target partial dependence style binned plot.
- Binned target mean by numeric feature.
- Target mean by category.
- Target variance by category.
- Heteroscedasticity hints.
- Residual-like diagnostics if predictions provided.
- Leakage candidates.
- Monotonic relationship hints.

### Classification Target

- Class balance.
- Rare class count.
- Target entropy.
- Feature class separation.
- Class-conditional distributions.
- Weight of evidence.
- Information value.
- Lift by feature quantile.
- Gains by feature quantile.
- Target rate by category.
- Target rate confidence intervals.
- Calibration-style binning for probability columns.
- Label leakage candidates.
- Potential proxy variables.

### Survival Or Time-To-Event Target Later

- Censoring rate.
- Event rate.
- Kaplan-Meier curves.
- Nelson-Aalen cumulative hazard.
- Survival by group.
- Log-rank test.
- Time-varying missingness.

## Feature Engineering Suggestions

- Numeric transform suggestions: log, log1p, Box-Cox, Yeo-Johnson, rank, quantile,
  winsorize, standardize, robust-scale.
- Categorical encoding suggestions: one-hot, frequency, target encoding with
  leakage cautions, ordinal, hashing.
- Datetime feature suggestions: year, quarter, month, weekday, hour, holiday,
  elapsed time, time since prior event.
- Text feature suggestions: length, token count, TF-IDF, embeddings optional.
- Missingness indicator suggestions.
- Rare-category grouping suggestions.
- Unit normalization suggestions.
- Type conversion suggestions.
- Column splitting suggestions.
- Nested column flattening suggestions.
- Interaction candidate suggestions.
- Redundant feature removal suggestions.
- Leakage removal suggestions.

## Statistical Tests And Diagnostics Catalog

### Normality And Distribution Fit

- Shapiro-Wilk test.
- D'Agostino-Pearson test.
- Anderson-Darling test.
- Kolmogorov-Smirnov test.
- Lilliefors correction optional.
- Jarque-Bera test.
- Cramer-von Mises test.
- Chi-square goodness-of-fit.
- Probability plot correlation coefficient.
- AIC/BIC comparison across candidate distributions.
- Bootstrap goodness-of-fit.

### Variance And Scale

- Levene test.
- Brown-Forsythe test.
- Bartlett test.
- Fligner-Killeen test.
- Ansari-Bradley test.
- Mood scale test.
- Rolling variance diagnostics.

### Location Differences

- One-sample t-test.
- Two-sample t-test.
- Welch t-test.
- Paired t-test.
- Wilcoxon signed-rank test.
- Mann-Whitney U test.
- Brunner-Munzel test.
- Sign test.
- Median test.
- ANOVA.
- Welch ANOVA.
- Repeated-measures ANOVA later.
- Kruskal-Wallis.
- Friedman test.
- Permutation tests.
- Bootstrap intervals.

### Association And Independence

- Chi-square independence.
- Fisher exact.
- Barnard exact optional.
- Boschloo exact optional.
- G-test.
- Pearson correlation test.
- Spearman correlation test.
- Kendall tau test.
- Distance correlation test.
- Mutual information permutation test.
- HSIC optional.

### Time Series

- Augmented Dickey-Fuller.
- KPSS.
- Phillips-Perron optional.
- Ljung-Box.
- Box-Pierce.
- Durbin-Watson.
- Breusch-Godfrey optional.
- ARCH test.
- Seasonal strength.
- Change-point tests optional.

### Multiple Testing And Practical Significance

- Benjamini-Hochberg false discovery rate.
- Bonferroni correction.
- Holm correction.
- Effect sizes always near p-values.
- Confidence intervals near effect sizes.
- Warnings for large-sample trivial significance.
- Warnings for small-sample instability.

## Visualization System Requirements

### Plot Qualities

- Always state data used: full, sampled, aggregated, metadata-only.
- Always state transformation applied.
- Always expose binning choices.
- Always expose smoothing choices.
- Always expose uncertainty when relevant.
- Prefer readable defaults.
- Support static outputs.
- Support interactive outputs later.
- Support notebook display.
- Support saving to PNG/SVG/HTML.
- Support plot specs that can be rendered by multiple backends.

### Plot Backends

- Matplotlib for stable static output.
- Seaborn for statistical plot defaults.
- Plotly for interactive reports.
- Altair/Vega-Lite for declarative grammar and JSON specs.
- hvPlot/Datashader later for large data.
- Rich/textual terminal summaries for CLI.

## Report Sections

- Executive summary.
- Dataset shape.
- Storage shape.
- Schema and types.
- Quality warnings.
- Missingness.
- Numeric distributions.
- Categorical distributions.
- Datetime behavior.
- Text behavior.
- Relationships.
- Multivariate structure.
- Outliers.
- Concentration and imbalance.
- Drift/comparison.
- Target-aware EDA.
- Suggested cleaning actions.
- Suggested contracts.
- Suggested feature engineering.
- Reproducibility appendix.

## Issue Ranking

Every automated warning should include:

- Severity.
- Confidence.
- Affected columns.
- Affected rows when available.
- Why it matters.
- Suggested next action.
- Method used.
- Whether finding is exact or approximate.
- Whether finding came from data scan or metadata only.

Potential issue categories:

- Correctness risk.
- Modeling risk.
- Leakage risk.
- Performance risk.
- Storage risk.
- Interpretability risk.
- Fairness/privacy risk.
- Operational drift risk.
- Human readability issue.

## MVP Candidates

The first version should not try to implement everything above. A strong MVP:

- `profile()` for pandas DataFrames and Parquet paths.
- Dataset summary.
- Column summaries.
- Missingness analysis.
- Numeric distribution stats.
- Categorical frequency and concentration stats.
- Datetime summaries.
- Basic plots.
- Lorenz/concentration/Pareto plots.
- Pairwise correlations.
- Simple relationship scan.
- Parquet metadata scan.
- Issue ranking.
- `compare()` for two profiles.
- Markdown/HTML/JSON export.
- CLI: `stateframe profile data/*.parquet`.

## Differentiators To Protect

- Parquet-native EDA before loading all rows.
- Data-shape language: grain, keys, concentration, drift, storage skew.
- Advanced metrics with plain-English interpretation.
- One API for exact, approximate, and metadata-only profiles.
- Diffable profiles.
- EDA-to-contract generation.
- A tiny API surface that unlocks a large diagnostic catalog.
