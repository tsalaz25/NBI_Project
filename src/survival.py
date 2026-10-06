# Kaplan-Meier Vurves: Time until a Component Rating <= 4
#
#    pip install -r requirements-analysis.txt
#    python -m src.survival                          # superstructure, threshold 4
#    python -m src.survival --component DECK
#    python -m src.survival --threshold 5
#
# Writes reports/km_<component>.png and prints a summary.
#
# Handles Right Censoring and Left Truncation... See README


from __future__ import annotations
import argparse
import sys
import matplotlib
matplotlib.use("Agg")                    # write files; no window needed
import matplotlib.pyplot as plt          # noqa: E402
import pandas as pd                      # noqa: E402
from lifelines import KaplanMeierFitter  # noqa: E402
from src import config, db              # noqa: E402

# Item 43A, Type of material/design
MATERIAL = {
    "1": "Concrete", "2": "Concrete",
    "3": "Steel", "4": "Steel",
    "5": "Prestressed concrete",
    "6": "Prestressed concrete",
    "7": "Timber",
}
REPORTS = config.ROOT / "reports"


def load_lifecycle(conn, component: str, threshold: int) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SELECT refresh_lifecycle(%s)", (threshold,))
        cur.execute(
            """
            SELECT l.asset_id, l.entry_age, l.duration_years, l.event_observed,
                   l.excluded_reason, a.structure_kind
            FROM lifecycle l
            JOIN asset a USING (asset_id)
            WHERE l.component = %s
            """,
            (component,),
        )
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    conn.commit()
    df = pd.DataFrame(rows, columns=cols)
    df["material"] = df["structure_kind"].map(MATERIAL).fillna("Other")
    return df


def fit(df: pd.DataFrame, label: str, truncation: bool = True) -> KaplanMeierFitter:
    km = KaplanMeierFitter()
    km.fit(
        durations=df["duration_years"].astype(float),
        event_observed=df["event_observed"].astype(bool),
        entry=df["entry_age"].astype(float) if truncation else None,
        label=label,
    )
    return km


def _median(km: KaplanMeierFitter) -> str:
    m = km.median_survival_time_
    return "not reached" if m == float("inf") else f"{m:.0f}"


def _surv_at(km: KaplanMeierFitter, age: float) -> str:
    return f"{float(km.predict(age)):.2f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--component", default="SUPERSTRUCTURE",
                    choices=["DECK", "SUPERSTRUCTURE", "SUBSTRUCTURE", "CULVERT"])
    ap.add_argument("--threshold", type=int, default=4)
    ap.add_argument("--min-group", type=int, default=30,
                    help="smallest material group to plot")
    args = ap.parse_args(argv)

    conn = db.connect()
    try:
        df = load_lifecycle(conn, args.component, args.threshold)
    finally:
        conn.close()

    if df.empty:
        print("lifecycle is empty: load data first (python -m src.load)")
        return 1

    # What data wnet in and What Data was Excluded, Why?
    print(f"\n{args.component}, failure = first rating <= {args.threshold}\n")
    status = df["excluded_reason"].fillna("(used)").value_counts()
    print("bridges by status:")
    print(status.to_string(), "\n")

    used = df[df["excluded_reason"].isna()].copy()
    n_events = int(used["event_observed"].sum())
    print(f"used: {len(used):,} bridges | {n_events:,} reached the threshold | "
          f"{len(used) - n_events:,} right-censored "
          f"({100 * (1 - n_events / len(used)):.0f}%)")
    print(f"entry age: median {used['entry_age'].median():.0f}, "
          f"max {used['entry_age'].max():.0f} (left truncation)\n")

    # Fits
    groups = (used.groupby("material").size()
              .loc[lambda s: s >= args.min_group]
              .sort_values(ascending=False))
    rows = []
    REPORTS.mkdir(exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), sharey=True)

    for material in groups.index:
        sub = used[used["material"] == material]
        km = fit(sub, f"{material} (n={len(sub)})")
        km.plot_survival_function(ax=ax1, ci_show=True)
        rows.append((material, len(sub), int(sub["event_observed"].sum()),
                     _median(km), _surv_at(km, 50), _surv_at(km, 75)))

    km_all = fit(used, "Left truncation handled (entry age)")
    km_naive = fit(used, "Naive: everyone at risk from age 0", truncation=False)
    km_all.plot_survival_function(ax=ax2, ci_show=True)
    km_naive.plot_survival_function(ax=ax2, ci_show=False, linestyle="--")

    ax1.set_title(f"{args.component.title()}: time to rating <= {args.threshold}, by material")
    ax2.set_title("All bridges: effect of left truncation")
    for ax in (ax1, ax2):
        ax.set_xlabel("Age (years)")
        ax.grid(alpha=0.3)
    ax1.set_ylabel(f"P(rating still > {args.threshold})")
    ax1.set_ylim(0, 1.02)
    fig.tight_layout()
    out = REPORTS / f"km_{args.component.lower()}.png"
    fig.savefig(out, dpi=150)

    # Summary
    summary = pd.DataFrame(rows, columns=["material", "n", "events", "median age",
                                          "S(50)", "S(75)"])
    print(summary.to_string(index=False))
    print(f"\nall bridges, median age to threshold: "
          f"{_median(km_all)} with truncation vs {_median(km_naive)} naive")
    print(f"all bridges, S(50): {_surv_at(km_all, 50)} with truncation vs "
          f"{_surv_at(km_naive, 50)} naive")
    print(f"\nchart: {out.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
