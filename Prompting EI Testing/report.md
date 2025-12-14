# EQBench3 Complete Evaluation Report

**Date**: 2025-12-14 21:27
**Total Scenarios**: 45
**Scoring Scale**: 0-20 per criterion (max 100 total)

---

## Score Anchoring Reference

- **0-4**: Poor, major deficiencies
- **5**: High school level
- **10**: Graduate level
- **15**: PhD level
- **19-20**: Top 0.001% (Rogers/Jung level)

## Overall Rankings

| Rank | Prompt | Mean Score | Std Dev | Range | Median | Avg per Criterion |
|------|--------|-----------|---------|-------|--------|------------------|
| 1 | prompt_avi | 77.09/100 | 5.27 | 62.0-89.0 | 77.00 | 15.42/20 |
| 2 | prompt_ei | 75.87/100 | 5.14 | 62.0-84.0 | 76.00 | 15.17/20 |
| 3 | human_guidance | 74.31/100 | 6.63 | 52.0-89.0 | 75.00 | 14.86/20 |
| 4 | prompt_prose | 71.58/100 | 6.55 | 54.0-84.0 | 72.00 | 14.32/20 |
| 5 | baseline | 68.69/100 | 9.77 | 36.0-84.0 | 69.00 | 13.74/20 |

## Criteria Breakdown (0-20 scale)

| Prompt | Empathy | Insight | Context | Theory of Mind | Depth |
|--------|---------|---------|---------|----------------|-------|
| prompt_avi | 15.04 | 15.93 | 15.13 | 16.04 | 14.93 |
| prompt_ei | 14.71 | 15.69 | 15.02 | 15.78 | 14.67 |
| human_guidance | 14.04 | 15.29 | 15.02 | 15.38 | 14.58 |
| prompt_prose | 13.38 | 14.93 | 14.20 | 14.98 | 14.09 |
| baseline | 12.80 | 14.49 | 13.62 | 14.40 | 13.38 |

## Improvement over Baseline

| Prompt | Absolute Difference | Relative Improvement |
|--------|-------------------|---------------------|
| prompt_avi | +8.40 | +12.2% |
| prompt_ei | +7.18 | +10.4% |
| human_guidance | +5.62 | +8.2% |
| prompt_prose | +2.89 | +4.2% |

## Human Guidance Analysis

*Guided prompt was not tested in this run.*

## Statistical Summary

### prompt_avi
- **Scenarios tested**: 45
- **Mean**: 77.09/100
- **Median**: 77.00/100
- **Std Dev**: 5.27
- **Range**: 62.0 - 89.0
- **Coefficient of Variation**: 6.8%

### prompt_ei
- **Scenarios tested**: 45
- **Mean**: 75.87/100
- **Median**: 76.00/100
- **Std Dev**: 5.14
- **Range**: 62.0 - 84.0
- **Coefficient of Variation**: 6.8%

### human_guidance
- **Scenarios tested**: 45
- **Mean**: 74.31/100
- **Median**: 75.00/100
- **Std Dev**: 6.63
- **Range**: 52.0 - 89.0
- **Coefficient of Variation**: 8.9%

### prompt_prose
- **Scenarios tested**: 45
- **Mean**: 71.58/100
- **Median**: 72.00/100
- **Std Dev**: 6.55
- **Range**: 54.0 - 84.0
- **Coefficient of Variation**: 9.1%

### baseline
- **Scenarios tested**: 45
- **Mean**: 68.69/100
- **Median**: 69.00/100
- **Std Dev**: 9.77
- **Range**: 36.0 - 84.0
- **Coefficient of Variation**: 14.2%

## Generated Visualizations

1. `score_distributions.png` - Score histograms for each prompt
2. `criteria_breakdown.png` - Grouped bar chart of criteria performance
3. `score_variance.png` - Mean scores with error bars
4. `radar_chart.png` - Multi-criteria radar comparison

## Introspection Quality Summary

| Prompt | Total Turns | Missing Self | Missing Other | Avg Self Length | Avg Other Length |
|--------|-------------|--------------|---------------|-----------------|------------------|
| baseline | 135 | 22.2% | 22.2% | 309 | 313 |
| human_guidance | 135 | 33.3% | 33.3% | 292 | 275 |
| prompt_avi | 135 | 3.7% | 3.7% | 301 | 311 |
| prompt_ei | 135 | 15.6% | 15.6% | 313 | 319 |
| prompt_prose | 135 | 4.4% | 4.4% | 310 | 308 |

