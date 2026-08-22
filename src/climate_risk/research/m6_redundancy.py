"""M6 collinearity/redundancy diagnostics.

n=19 (the full G20 sovereign panel) is small for any of these diagnostics --
correlation estimates are noisy and VIF can be unstable or undefined when
the design matrix is close to singular. Every function here says so in its
output rather than presenting a number without that caveat; nothing here
is a hard statistical test, all of it is descriptive evidence to weigh
alongside the incremental-information test in `m6_incremental`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

CANDIDATE_FEATURE_COLUMNS = [
    "carbon_intensity_trend",
    "coupling_elasticity",
    "coal_share_elec",
    "fossil_share_elec",
    "renewables_share_elec",
    "low_carbon_share_elec",
    "coal_trend_pp_per_year",
    "clean_power_momentum_pp_per_year",
    "renewable_buildout_rate_pp_per_year",
    "fossil_persistence_mean_pct",
    "transition_velocity",
    "stalled_transition_residual_pp",
]

# Redundancy-grouping threshold: features whose pairwise |Spearman rho| >=
# this are merged into the same cluster. 0.7 is a conventional "strong
# correlation" cutoff, not tuned against this dataset's results.
REDUNDANCY_CLUSTER_THRESHOLD = 0.7


def correlation_matrices(
    evaluation_panel: pd.DataFrame, *, columns: list[str] = CANDIDATE_FEATURE_COLUMNS
) -> dict[str, pd.DataFrame]:
    frame = evaluation_panel[columns]
    return {
        "pearson": frame.corr(method="pearson", min_periods=5),
        "spearman": frame.corr(method="spearman", min_periods=5),
    }


def variance_inflation_factors(
    evaluation_panel: pd.DataFrame, *, columns: list[str] = CANDIDATE_FEATURE_COLUMNS
) -> pd.DataFrame:
    """Listwise-deleted VIF per feature. Returns a `note` column instead of
    silently proceeding when there isn't enough complete-case data or the
    design matrix is (near-)singular -- both expected at n=19 with up to 12
    correlated candidates."""
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    complete = evaluation_panel[columns].dropna()
    n_complete = len(complete)
    min_rows_required = len(columns) + 2  # need more observations than predictors to be meaningful

    if n_complete < min_rows_required:
        return pd.DataFrame(
            {
                "feature": columns,
                "vif": [None] * len(columns),
                "n_complete_case_rows": n_complete,
                "note": [
                    f"insufficient complete-case rows ({n_complete} < {min_rows_required} "
                    "needed) -- VIF not computed"
                ]
                * len(columns),
            }
        )

    design = complete.to_numpy(dtype=float)
    rows = []
    for i, column in enumerate(columns):
        try:
            vif = float(variance_inflation_factor(design, i))
        except (np.linalg.LinAlgError, ZeroDivisionError):
            vif = None
        rows.append(
            {
                "feature": column,
                "vif": vif,
                "n_complete_case_rows": n_complete,
                "note": "near-singular design matrix" if vif is None else "",
            }
        )
    return pd.DataFrame(rows)


def redundancy_groups(
    evaluation_panel: pd.DataFrame,
    *,
    columns: list[str] = CANDIDATE_FEATURE_COLUMNS,
    threshold: float = REDUNDANCY_CLUSTER_THRESHOLD,
) -> pd.DataFrame:
    """Hierarchical clustering on 1 - |Spearman rho| distance -- groups
    features that carry largely duplicated information (e.g. renewables/
    fossil/low-carbon shares, which are mechanically related power-mix
    identities) rather than scoring each as independent evidence.
    """
    spearman = evaluation_panel[columns].corr(method="spearman", min_periods=5)
    spearman = spearman.fillna(0.0)  # no measurable relationship -> treat as maximally distant
    distance = (1.0 - spearman.abs()).to_numpy(dtype=float, copy=True)
    np.fill_diagonal(distance, 0.0)

    condensed = squareform(distance, checks=False)
    linkage_matrix = linkage(condensed, method="average")
    cluster_ids = fcluster(linkage_matrix, t=1.0 - threshold, criterion="distance")

    return (
        pd.DataFrame({"feature": columns, "redundancy_group": cluster_ids})
        .sort_values(["redundancy_group", "feature"])
        .reset_index(drop=True)
    )
