# Robustness audit of the Belo Horizonte ITBI dashboard

## Provenance

- Source revision `5908d77ed56fc9adb6dbafaf2cb38f34245bcd76`
- Source SHA-256 `386a922d539e78538cd31dd21f7f3ed32db7505ecc70d16a683f69aadf7dbe86`
- Cached transaction table verified: **True**
- Model version `v5` and audit version `v1`
- Protocol `hedonic-sensitivity-v1` with SHA-256 `f053d9ea55d47b3e16b95734ab8114c1fece0c706865f7d1460f352aaf1a9724`
- Seed 20261122, 200 trajectory bootstrap draws, 1000 draws per quarterly median bootstrap and 2 numerical threads

The cached-table hash, Git state and software versions are in [manifest.json](manifest.json).

## Target and observable population

**Scientific target.** The evolution of inflation-adjusted declared values of residential properties transferred in arm's-length market sales in Belo Horizonte, adjusted for the characteristics observed in the hedonic specification.

**Observable population.** Eligible residential ITBI records (apartments and houses) with a declared value, a positive built area and complete model characteristics. ITBI covers onerous transfers of any nature. The municipal source has no field for the nature of the transfer or the date of the underlying contract, so membership in the target population is unobserved. No rule in this audit identifies arm's-length market sales. Every screen defines an operational proxy population and is reported as such.

**Source definitions recorded, not verified here.** According to the municipal data dictionary, the published built area is the unit's built area multiplied by the acquired percentage ("Área Construída Adquirida"), and the tax base is the market value of the rights transferred ("Valor Base Cálculo"). Whether the harmonised `built_area_m2` maps to "Área Construída Adquirida" remains to be confirmed against the raw files.

## Protocol

All screens remove records from the published model population. Neighbourhood eligibility is applied once to that population. The fixed comparisons of separately estimated property types address the common trend imposed by the pooled model.

| Specification | Family | Retained rows | Estimator |
| --- | --- | --- | --- |
| baseline | reference | Retain the published model population | OLS |
| price_floor_0500 | real price floor | Real price per m² ≥ R$500 | OLS |
| price_floor_0750 | real price floor | Real price per m² ≥ R$750 | OLS |
| price_floor_1000 | real price floor | Real price per m² ≥ R$1,000 | OLS |
| price_floor_1250 | real price floor | Real price per m² ≥ R$1,250 | OLS |
| price_floor_1500 | real price floor | Real price per m² ≥ R$1,500 | OLS |
| price_ceiling_30000 | real price ceiling | Real price per m² ≤ R$30,000 | OLS |
| ratio_floor_030 | declared/base floor | Declared/base ≥ 0.30 | OLS |
| ratio_floor_040 | declared/base floor | Declared/base ≥ 0.40 | OLS |
| ratio_floor_050 | declared/base floor | Declared/base ≥ 0.50 | OLS |
| ratio_floor_060 | declared/base floor | Declared/base ≥ 0.60 | OLS |
| ratio_floor_070 | declared/base floor | Declared/base ≥ 0.70 | OLS |
| area_20_1000 | area window | Area in [20, 1,000] m² | OLS |
| combined_reference_v2 | reference audit screen | Real price per m² in [R$1,000, R$30,000] and area in [20, 1,000] m² | OLS |
| apartments_only | property type | Apartments only | OLS |
| houses_only | property type | Houses only | OLS |
| huber_global | estimator | Retain the published model population | Huber (global scale) |
| huber_year | estimator | Retain the published model population | Huber (year scales) |

Huber clips the residual score at ±k and minimises quadratic loss inside those bounds and linear loss outside, conditional on the final thresholds. The thresholds are 1.345 times the residual MAD divided by 0.6744897501960817, using a global scale or a scale for each calendar year. The year-specific fit changes only the threshold. Standardised Huber loss would weight years by inverse scale squared even in the absence of clipping, changing the estimand. Both fits recover OLS in the absence of clipping.

Huber estimates start at OLS and use iteratively reweighted least squares. The maximum coefficient change and maximum relative scale change must both be below 1e-09 within 200 iterations. The audit also checks the score, the fixed point and the weighted quarterly residual means. All specifications have pointwise 95% intervals based on their own neighbourhood-clustered covariance.

## Baseline reproduction

The baseline reproduced the published quarterly index, intervals and fit metadata within relative tolerance 1e-09. The OLS fit has 202,204 records, R² 0.237 and residual SD 0.437 log points.

## Specification summary

| Specification | n | 2016Q3 | 2025Q4 [95% interval] | Max absolute log deviation | Quarter |
| --- | --- | --- | --- | --- | --- |
| baseline | 202,204 | 88.34 | 110.04 [107.17, 112.98] | 0.00000 | 2016Q1 |
| price_floor_0500 | 200,707 | 91.32 | 109.08 [106.06, 112.19] | 0.03322 | 2016Q3 |
| price_floor_0750 | 199,246 | 93.23 | 108.26 [105.32, 111.29] | 0.05385 | 2016Q3 |
| price_floor_1000 | 197,618 | 93.72 | 106.61 [103.62, 109.69] | 0.05909 | 2016Q3 |
| price_floor_1250 | 195,879 | 95.40 | 105.27 [102.16, 108.46] | 0.07692 | 2016Q3 |
| price_floor_1500 | 194,215 | 96.53 | 104.55 [101.49, 107.69] | 0.08869 | 2016Q3 |
| price_ceiling_30000 | 202,184 | 88.31 | 110.11 [107.24, 113.06] | 0.00077 | 2019Q4 |
| ratio_floor_030 | 196,426 | 92.12 | 104.32 [101.35, 107.39] | 0.06913 | 2024Q2 |
| ratio_floor_040 | 193,456 | 92.60 | 102.04 [99.13, 105.03] | 0.09083 | 2024Q2 |
| ratio_floor_050 | 189,819 | 93.44 | 100.65 [97.61, 103.79] | 0.10597 | 2024Q2 |
| ratio_floor_060 | 184,865 | 93.64 | 99.79 [96.77, 102.90] | 0.11954 | 2024Q1 |
| ratio_floor_070 | 177,316 | 93.39 | 99.12 [96.19, 102.14] | 0.13253 | 2024Q2 |
| area_20_1000 | 201,737 | 90.71 | 109.92 [107.14, 112.77] | 0.02641 | 2016Q3 |
| combined_reference_v2 | 197,280 | 93.95 | 106.62 [103.64, 109.69] | 0.06155 | 2016Q3 |
| apartments_only | 181,276 | 87.57 | 110.36 [107.30, 113.51] | 0.01847 | 2021Q2 |
| houses_only | 20,928 | 95.03 | 109.56 [100.87, 118.99] | 0.16848 | 2022Q1 |
| huber_global | 202,204 | 94.67 | 105.00 [102.13, 107.94] | 0.06918 | 2016Q3 |
| huber_year | 202,204 | 94.51 | 105.44 [102.57, 108.38] | 0.06753 | 2016Q3 |

## Selected quarters

The full trajectories and log deviations are in [index_trajectories.csv](index_trajectories.csv).

| spec id | 2016Q3 | 2019Q4 | 2021Q4 | 2023Q4 | 2025Q4 |
| --- | --- | --- | --- | --- | --- |
| baseline | 88.34 | 96.54 | 95.21 | 101.92 | 110.04 |
| price_floor_0500 | 91.32 | 95.47 | 95.02 | 101.49 | 109.08 |
| price_floor_0750 | 93.23 | 94.88 | 94.94 | 100.64 | 108.26 |
| price_floor_1000 | 93.72 | 94.49 | 93.94 | 98.95 | 106.61 |
| price_floor_1250 | 95.40 | 93.92 | 93.03 | 97.92 | 105.27 |
| price_floor_1500 | 96.53 | 93.77 | 92.83 | 97.28 | 104.55 |
| price_ceiling_30000 | 88.31 | 96.62 | 95.27 | 101.99 | 110.11 |
| ratio_floor_030 | 92.12 | 93.73 | 91.68 | 96.33 | 104.32 |
| ratio_floor_040 | 92.60 | 92.70 | 90.43 | 94.24 | 102.04 |
| ratio_floor_050 | 93.44 | 92.05 | 89.70 | 92.94 | 100.65 |
| ratio_floor_060 | 93.64 | 91.45 | 88.84 | 91.53 | 99.79 |
| ratio_floor_070 | 93.39 | 90.69 | 87.88 | 90.21 | 99.12 |
| area_20_1000 | 90.71 | 96.46 | 95.19 | 101.81 | 109.92 |
| combined_reference_v2 | 93.95 | 94.54 | 94.02 | 98.94 | 106.62 |
| apartments_only | 87.57 | 95.30 | 93.71 | 101.07 | 110.36 |
| houses_only | 95.03 | 109.08 | 107.79 | 110.10 | 109.56 |
| huber_global | 94.67 | 93.65 | 92.06 | 96.72 | 105.00 |
| huber_year | 94.51 | 94.14 | 92.69 | 97.26 | 105.44 |

## Exclusion composition

Annual shares use each year's published-model records as the denominator. [exclusions.csv](exclusions.csv) also gives counts and shares by property type.

| spec id | family | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| price_floor_0500 | real price floor | 1.4% | 1.2% | 0.9% | 0.8% | 0.5% | 0.6% | 0.6% | 0.6% | 0.5% | 0.6% |
| price_floor_0750 | real price floor | 2.7% | 2.2% | 1.9% | 1.6% | 1.0% | 1.1% | 1.3% | 1.3% | 1.0% | 1.1% |
| price_floor_1000 | real price floor | 4.1% | 3.3% | 2.9% | 2.6% | 1.6% | 1.8% | 1.9% | 1.9% | 1.6% | 1.6% |
| price_floor_1250 | real price floor | 5.8% | 4.8% | 4.0% | 3.5% | 2.3% | 2.4% | 2.6% | 2.6% | 2.3% | 2.1% |
| price_floor_1500 | real price floor | 7.2% | 6.0% | 5.3% | 4.5% | 2.9% | 3.0% | 3.3% | 3.3% | 2.8% | 2.7% |
| price_ceiling_30000 | real price ceiling | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| ratio_floor_030 | declared/base floor | 5.8% | 5.0% | 4.1% | 3.7% | 2.2% | 2.0% | 2.0% | 1.9% | 1.5% | 1.8% |
| ratio_floor_040 | declared/base floor | 8.8% | 7.8% | 6.4% | 5.5% | 3.4% | 3.2% | 2.9% | 2.8% | 2.3% | 2.5% |
| ratio_floor_050 | declared/base floor | 11.9% | 11.2% | 9.0% | 7.7% | 4.9% | 4.6% | 4.3% | 3.9% | 3.3% | 3.7% |
| ratio_floor_060 | declared/base floor | 15.7% | 15.2% | 12.6% | 10.9% | 7.5% | 6.4% | 6.0% | 5.2% | 4.8% | 5.8% |
| ratio_floor_070 | declared/base floor | 21.1% | 21.2% | 18.3% | 16.2% | 11.3% | 9.1% | 8.3% | 7.2% | 7.1% | 9.2% |
| area_20_1000 | area window | 1.0% | 0.6% | 0.5% | 0.3% | 0.0% | 0.1% | 0.0% | 0.0% | 0.0% | 0.1% |
| combined_reference_v2 | reference audit screen | 4.6% | 3.9% | 3.4% | 2.8% | 1.6% | 1.8% | 2.0% | 1.9% | 1.6% | 1.7% |
| apartments_only | property type | 10.7% | 11.3% | 11.5% | 10.6% | 10.3% | 9.9% | 10.3% | 9.7% | 9.6% | 10.3% |
| houses_only | property type | 89.3% | 88.7% | 88.5% | 89.4% | 89.7% | 90.1% | 89.7% | 90.3% | 90.4% | 89.7% |

## Huber weights and residual dispersion

Shares use the weights from the final solve. Annual scales are in log points. The year-by-type detail is in [huber_weights.csv](huber_weights.csv).

| spec id | year | scale | share downweighted |
| --- | --- | --- | --- |
| huber_global | 2016 | 0.241 | 0.298 |
| huber_global | 2017 | 0.241 | 0.287 |
| huber_global | 2018 | 0.241 | 0.262 |
| huber_global | 2019 | 0.241 | 0.246 |
| huber_global | 2020 | 0.241 | 0.212 |
| huber_global | 2021 | 0.241 | 0.207 |
| huber_global | 2022 | 0.241 | 0.226 |
| huber_global | 2023 | 0.241 | 0.223 |
| huber_global | 2024 | 0.241 | 0.232 |
| huber_global | 2025 | 0.241 | 0.231 |
| huber_year | 2016 | 0.269 | 0.262 |
| huber_year | 2017 | 0.272 | 0.247 |
| huber_year | 2018 | 0.253 | 0.245 |
| huber_year | 2019 | 0.238 | 0.251 |
| huber_year | 2020 | 0.224 | 0.237 |
| huber_year | 2021 | 0.216 | 0.244 |
| huber_year | 2022 | 0.227 | 0.244 |
| huber_year | 2023 | 0.233 | 0.235 |
| huber_year | 2024 | 0.248 | 0.223 |
| huber_year | 2025 | 0.248 | 0.222 |

Records below R$1,000/m² carry 20.0% of the `huber_global` weight deficit.

Records below R$1,000/m² carry 19.9% of the `huber_year` weight deficit.

**Baseline OLS residual MAD scale, in log points**

| year | all records | excluding low tail |
| --- | --- | --- |
| 2016 | 0.285 | 0.265 |
| 2017 | 0.285 | 0.274 |
| 2018 | 0.265 | 0.254 |
| 2019 | 0.246 | 0.236 |
| 2020 | 0.231 | 0.226 |
| 2021 | 0.228 | 0.223 |
| 2022 | 0.233 | 0.228 |
| 2023 | 0.237 | 0.232 |
| 2024 | 0.252 | 0.246 |
| 2025 | 0.251 | 0.244 |

## Descriptive diagnostics

**Price tails.** 205,436 eligible records have positive area.

| probability | price real |
| --- | --- |
| 0.001 | 194.673 |
| 0.010 | 572.784 |
| 0.020 | 874.981 |
| 0.500 | 4,543.565 |
| 0.980 | 9,483.730 |
| 0.990 | 10,459.588 |
| 0.999 | 15,079.611 |

| year | share below 1000 | share above 30000 |
| --- | --- | --- |
| 2016 | 4.382% | 0.021% |
| 2017 | 3.581% | 0.025% |
| 2018 | 3.207% | 0.035% |
| 2019 | 2.823% | 0.005% |
| 2020 | 1.750% | 0.011% |
| 2021 | 1.865% | 0.004% |
| 2022 | 2.081% | 0.009% |
| 2023 | 2.045% | 0.005% |
| 2024 | 1.684% | 0.000% |
| 2025 | 1.736% | 0.000% |

**Low-tail profile and fraction windows.** Counts at each fraction use ±0.003. The side counts are averaged over windows centred 0.012 to either side.

| price group | n | share houses | median area | median declared | median declared base | share ratio below half | median real base per m2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| at_or_above_1000 | 200440 | 0.104 | 103.870 | 339800.030 | 1.000 | 0.041 | 4998.898 |
| below_1000 | 4996 | 0.400 | 122.800 | 50000.000 | 0.180 | 0.946 | 3406.586 |

| fraction | at fraction | mean beside |
| --- | --- | --- |
| 1/2 | 9 | 3.000 |
| 1/3 | 26 | 23.500 |
| 1/4 | 63 | 76.000 |
| 1/5 | 123 | 109.500 |
| 1/6 | 134 | 150.000 |
| 1/8 | 120 | 108.000 |
| 1/10 | 100 | 118.000 |

**Reach of a declared/base floor of 0.50.**

| year | low tail median ratio | low tail share ratio ge 0999 | share ratio below half | share flags at or above 1000 |
| --- | --- | --- | --- | --- |
| 2016 | 0.171 | 0.020 | 0.122 | 0.685 |
| 2017 | 0.157 | 0.000 | 0.116 | 0.696 |
| 2018 | 0.169 | 0.002 | 0.093 | 0.670 |
| 2019 | 0.163 | 0.000 | 0.079 | 0.655 |
| 2020 | 0.187 | 0.000 | 0.051 | 0.668 |
| 2021 | 0.188 | 0.006 | 0.047 | 0.621 |
| 2022 | 0.203 | 0.002 | 0.044 | 0.553 |
| 2023 | 0.205 | 0.000 | 0.040 | 0.510 |
| 2024 | 0.205 | 0.005 | 0.033 | 0.532 |
| 2025 | 0.175 | 0.005 | 0.038 | 0.558 |

**Adjacent-quarter changes.** Across 39 changes, observed variance is 0.000864 and mean estimated sampling variance is 0.000191 log points squared. The descriptive ratio is 0.221. Lag-1 autocorrelation is -0.313, with 1/√n = 0.160 as a white-noise reference.

**Tax-base comparisons.** 4 of 205,436 records with a positive tax base have declared values above it. Quarterly shares are in [diagnostics.json](diagnostics.json).

| year | share below | median declared base |
| --- | --- | --- |
| 2016 | 0.690 | 0.914 |
| 2017 | 0.726 | 0.906 |
| 2018 | 0.696 | 0.914 |
| 2019 | 0.664 | 0.928 |
| 2020 | 0.546 | 0.978 |
| 2021 | 0.457 | 1.000 |
| 2022 | 0.354 | 1.000 |
| 2023 | 0.273 | 1.000 |
| 2024 | 0.245 | 1.000 |
| 2025 | 0.421 | 1.000 |

**Round numbers.** Among 58,054 records in the dashboard's range, 58.6% are exact R$10,000 multiples and 22.2% are exact R$50,000 multiples. The second share divided by one fifth of the first is 1.90.

| width brl | share | uniform baseline |
| --- | --- | --- |
| 2500 | 0.234 | 0.050 |
| 5000 | 0.253 | 0.100 |
| 10000 | 0.302 | 0.200 |

**Quarterly neighbourhood medians.** Relative widths divide interval width by the sample median. Block-face draws take all records from each selected face. Quarterly intervals and counts are in [diagnostics.json](diagnostics.json).

| neighbourhood | n quarters | median record relative width | median block relative width | min share houses | max share houses |
| --- | --- | --- | --- | --- | --- |
| BURITIS | 40 | 8.5% | 11.5% | 0.4% | 5.0% |
| CASTELO | 40 | 8.7% | 10.0% | 1.2% | 7.6% |
| CENTRO | 40 | 19.7% | 20.7% | 0.0% | 1.5% |
| LOURDES | 40 | 17.7% | 22.5% | 0.0% | 3.5% |
| SAVASSI | 40 | 16.5% | 22.8% | 0.0% | 17.7% |

## Clustering stability and composition check

The published trajectories index annual apartment medians to the first year.

| Published group | Neighbourhoods |
| --- | --- |
| 1 | 3 |
| 2 | 24 |
| 3 | 35 |
| 4 | 32 |

| k | Silhouette |
| --- | --- |
| 2 | 0.352 |
| 3 | 0.245 |
| 4 | 0.253 |
| 5 | 0.219 |
| 6 | 0.202 |

**Sampling instability.** Across 200 draws, the adjusted Rand index against the published partition has median 0.450, P10 0.282 and P90 0.592. The endpoint bootstrap SE has median 4.49 and P90 7.45 index points. Resampling records independently omits within-cell dependence and is likely to overstate stability.

**Representation dependence.** All representations use the same K-means settings.

| representation | ari | silhouette |
| --- | --- | --- |
| mean_2016_2017 | 0.386 | 0.221 |
| series_mean | 0.217 | 0.133 |
| log_centred | 0.198 | 0.132 |

**Composition check.** The ratio of 2025 to 2016 apartment medians is indexed to 100 for all apartments and for the subset excluding the new age band. The table gives the median ratio in each published group. Neighbourhood ratios, endpoint counts, small-cell flags and membership are in [diagnostics.json](diagnostics.json).

| group | median all apartments | median excluding new |
| --- | --- | --- |
| 1 | 133.12 | 101.20 |
| 2 | 106.08 | 101.63 |
| 3 | 97.08 | 94.30 |
| 4 | 84.20 | 88.38 |

## Trajectory patterns

> The v1 annual typology (four groups on unadjusted medians indexed to 2016) was withdrawn after bootstrap agreement with the published partition reached a median ARI of 0.45. A rule proposed before any re-analysis (publish groups only if the bootstrap median ARI reaches 0.75) was not met by any specification tested: the best reached about 0.61. After inspecting those results, the publication criterion was changed: patterns are shown because their centres are stable under resampling, while membership is reported per neighbourhood and borderline neighbourhoods are identified as such. This change was made after seeing the data and is reported as such.

The chosen fit has inertia 0.6476067335 and the 34 / 47 / 22 alternative has inertia 0.6478202965, with Copacabana, Guarani, Manacas, Santa Amelia, Santa Monica switching between stable and rising and Luxemburgo switching assignment elsewhere.

| pattern | size | firm |
| --- | --- | --- |
| falling | 35 | 19 |
| stable | 51 | 10 |
| rising | 17 | 5 |

| resampling | ARI P10 | ARI median | ARI P90 | falling firm | stable firm | rising firm |
| --- | --- | --- | --- | --- | --- | --- |
| Block faces (published) | 0.174 | 0.321 | 0.454 | 19 | 10 | 5 |
| Independent records | 0.459 | 0.601 | 0.722 | 29 | 32 | 11 |

Block faces are resampled within each neighbourhood and biennium, with unmatched records treated as singleton faces. The five cells with the fewest block faces are listed below.

| neighbourhood | period | records | block faces | largest-face share |
| --- | --- | --- | --- | --- |
| MANTIQUEIRA | 2016–2017 | 128 | 8 | 68.8% |
| SANTA HELENA | 2018–2019 | 160 | 9 | 51.9% |
| SANTA HELENA | 2016–2017 | 103 | 9 | 72.8% |
| CALIFORNIA | 2022–2023 | 78 | 10 | 52.6% |
| CALIFORNIA | 2018–2019 | 62 | 13 | 29.0% |

Draws in which the three patterns are not identified mostly assign one centre to a single neighbourhood whose cell is dominated by one block face; a minimum block-face count per cell is deferred.

See [trajectory_patterns.json](trajectory_patterns.json) for the full estimates and membership shares.

## Interpretation rules

- Each screen defines an operational proxy population. Membership in the target is unobserved.
- Differences between specifications are descriptive. The estimates share records, and no
  joint covariance is estimated.
- Huber-weighted means depend on the fitted model.
- The adjacent-quarter variance ratio is descriptive.
- The tax-base series and contrasts establish no causal effects of legislation, tax
  administration or market behaviour.

## Limitations and open source questions

- The mapping of `built_area_m2` to the municipal acquired-area definition requires
  verification against the raw records.
- The municipal source contains neither transaction nature nor the underlying contract date.
- The Huber sandwich holds the estimated scales fixed. Its intervals are pointwise and
  model-dependent. A neighbourhood bootstrap of the Huber fits is deferred on
  computational grounds.
- Block faces approximate buildings. Records without a face match form singleton clusters.
