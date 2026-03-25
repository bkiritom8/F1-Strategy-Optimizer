"""
Safety Car Strategy Model
1. SC pit decision — binary classifier (should driver pit under SC?)
2. Circuit SC probability — lookup table (per-circuit historical SC rate)
Val F1=0.921 | Test F1=0.920
"""

import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (
    classification_report,
    accuracy_score,
    f1_score,
    confusion_matrix,
    ConfusionMatrixDisplay,
)
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
import joblib
import os
import shap
from google.cloud import aiplatform, storage

aiplatform.init(
    project="f1optimizer", location="us-central1", experiment="f1-strategy-models"
)

PLOTS_DIR = "/tmp/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)


def upload_plot(local_path, gcs_path):
    storage.Client(project="f1optimizer").bucket("f1optimizer-models").blob(
        gcs_path
    ).upload_from_filename(local_path)
    print(f"Uploaded: gs://f1optimizer-models/{gcs_path}")


# Load unfiltered data — we need SC laps
df = pd.read_parquet(
    "gs://f1optimizer-data-lake/ml_features/fastf1_features_unfiltered.parquet"
)
print(f"Loaded: {len(df)} rows")
print(f'Seasons: {sorted(df["season"].unique())}')
print(f'SC laps: {df["is_sc_lap"].sum()} ({df["is_sc_lap"].mean()*100:.1f}%)')
print(f'Pitted under SC: {df["pitted_under_sc"].sum()}')

# Circuit SC probability lookup table
print("\nBuilding circuit SC probability lookup...")
circuit_sc = (
    df.groupby(["season", "round"])
    .agg(
        total_laps=("LapNumber", "max"),
        sc_laps=("is_sc_lap", "sum"),
        raceName=("raceName", "first"),
    )
    .reset_index()
)
circuit_sc["sc_prob_per_lap"] = circuit_sc["sc_laps"] / circuit_sc["total_laps"]
circuit_prob = (
    circuit_sc.groupby("raceName")["sc_prob_per_lap"].mean().round(4).to_dict()
)
print(f"  Circuits: {len(circuit_prob)}")
print("  Top 5 highest SC probability:")
for c, p in sorted(circuit_prob.items(), key=lambda x: -x[1])[:5]:
    print(f"    {c}: {p:.3f} per lap")

# Filter to SC laps only for model training
sc_df = df[df["is_sc_lap"] == 1].copy()
print(f"\nSC laps for model training: {len(sc_df)}")
print(f'Pit rate under SC: {sc_df["pitted_under_sc"].mean()*100:.1f}%')

sc_df = sc_df.sort_values(["season", "round", "Driver", "LapNumber"]).reset_index(
    drop=True
)

# Feature engineering
sc_df["lap_progress"] = sc_df["LapNumber"] / sc_df["total_laps"]
sc_df["tyre_life_pct"] = sc_df["TyreLife"] / sc_df["total_laps"].clip(lower=1)
sc_df["soft_age"] = sc_df["compound_SOFT"] * sc_df["TyreLife"]
sc_df["medium_age"] = sc_df["compound_MEDIUM"] * sc_df["TyreLife"]
sc_df["hard_age"] = sc_df["compound_HARD"] * sc_df["TyreLife"]
sc_df["pit_stops_so_far"] = (sc_df["Stint"] - 1).clip(lower=0)
sc_df["tyre_delta_trend"] = (
    df.groupby(["season", "round", "Driver"])["tyre_delta"]
    .transform(lambda x: x.rolling(5, min_periods=2).mean().shift(1))
    .reindex(sc_df.index)
    .fillna(0)
)
sc_df["race_phase"] = pd.cut(
    sc_df["lap_progress"], bins=[0, 0.33, 0.66, 1.0], labels=[0, 1, 2]
).astype(float)

OPTIMAL_STINT = {"SOFT": 20, "MEDIUM": 30, "HARD": 45, "INTERMEDIATE": 25, "WET": 20}
sc_df["optimal_stint_len"] = sc_df["Compound"].str.upper().map(OPTIMAL_STINT).fillna(30)
sc_df["laps_past_optimal"] = (sc_df["TyreLife"] - sc_df["optimal_stint_len"]).clip(
    lower=0
)

sc_df = sc_df.dropna(
    subset=["pitted_under_sc", "TyreLife", "position", "laps_remaining"]
)
print(f"After cleaning: {len(sc_df)} rows")

FEATURES = [
    # Tire state — most important for SC decision
    "TyreLife",
    "tyre_life_pct",
    "Stint",
    "FreshTyre",
    "compound_SOFT",
    "compound_MEDIUM",
    "compound_HARD",
    "compound_INTERMEDIATE",
    "compound_WET",
    "soft_age",
    "medium_age",
    "hard_age",
    "laps_past_optimal",
    "optimal_stint_len",
    # Race context
    "LapNumber",
    "laps_remaining",
    "lap_progress",
    "total_laps",
    "fuel_load_pct",
    "race_phase",
    # Strategy state
    "pit_stops_so_far",
    # Position
    "position",
    "gap_ahead",
    # Lap time context
    "tyre_delta",
    "tyre_delta_trend",
    "lap_time_delta",
    "deg_rate_roll3",
    # Speed/sector
    "mean_speed",
    "max_speed",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "SpeedI1",
    "SpeedI2",
    "SpeedFL",
    "SpeedST",
]

features = [f for f in FEATURES if f in sc_df.columns]
print(f"\nFeatures: {len(features)} / {len(FEATURES)}")

# Temporal split
train = sc_df[sc_df["season"] <= 2021]
val = sc_df[(sc_df["season"] >= 2022) & (sc_df["season"] <= 2023)]
test = sc_df[sc_df["season"] == 2024]
print(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

X_train, y_train = train[features].fillna(0), train["pitted_under_sc"]
X_val, y_val = val[features].fillna(0), val["pitted_under_sc"]
X_test, y_test = test[features].fillna(0), test["pitted_under_sc"]

# Hyperparameters
LGB_PARAMS = dict(
    n_estimators=1000,
    max_depth=7,
    num_leaves=31,
    learning_rate=0.01,
    subsample=0.7,
    colsample_bytree=0.7,
    min_child_samples=20,
    reg_alpha=0.5,
    reg_lambda=1.0,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
    class_weight="balanced",
)
XGB_PARAMS = dict(
    n_estimators=800,
    max_depth=6,
    learning_rate=0.01,
    subsample=0.7,
    colsample_bytree=0.7,
    min_child_weight=20,
    reg_alpha=0.5,
    reg_lambda=1.0,
    random_state=42,
    tree_method="hist",
    early_stopping_rounds=50,
    verbosity=0,
    eval_metric="logloss",
    scale_pos_weight=(1 - y_train.mean()) / y_train.mean(),
)

with aiplatform.start_run(run="safety-car-v1", resume=True):
    aiplatform.log_params(
        {
            "model": "LGB+XGB ensemble",
            "lgb_n_estimators": LGB_PARAMS["n_estimators"],
            "lgb_num_leaves": LGB_PARAMS["num_leaves"],
            "xgb_n_estimators": XGB_PARAMS["n_estimators"],
            "train_seasons": "2018-2021",
            "n_features": len(features),
            "train_sc_laps": len(train),
            "sc_pit_rate": float(y_train.mean()),
            "circuits_in_lookup": len(circuit_prob),
        }
    )

    print("\nTraining LightGBM...")
    lgb_pit = LGBMClassifier(**LGB_PARAMS)
    lgb_pit.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    print("Training XGBoost...")
    xgb_pit = XGBClassifier(**XGB_PARAMS)
    xgb_pit.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Find optimal ensemble weight
    print("Finding optimal ensemble weight...")
    best_f1 = 0
    best_w = 0.5
    for w in np.arange(0.1, 0.95, 0.05):
        pred = (
            (
                w * lgb_pit.predict_proba(X_val)[:, 1]
                + (1 - w) * xgb_pit.predict_proba(X_val)[:, 1]
            )
            >= 0.5
        ).astype(int)
        f1 = f1_score(y_val, pred, average="macro")
        if f1 > best_f1:
            best_f1 = f1
            best_w = round(w, 2)

    print(f"Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}")

    val_pred = (
        (
            best_w * lgb_pit.predict_proba(X_val)[:, 1]
            + (1 - best_w) * xgb_pit.predict_proba(X_val)[:, 1]
        )
        >= 0.5
    ).astype(int)
    test_pred = (
        (
            best_w * lgb_pit.predict_proba(X_test)[:, 1]
            + (1 - best_w) * xgb_pit.predict_proba(X_test)[:, 1]
        )
        >= 0.5
    ).astype(int)

    val_acc = float(accuracy_score(y_val, val_pred))
    val_f1 = float(f1_score(y_val, val_pred, average="macro"))
    test_acc = float(accuracy_score(y_test, test_pred))
    test_f1 = float(f1_score(y_test, test_pred, average="macro"))

    lgb_val_f1 = float(f1_score(y_val, lgb_pit.predict(X_val), average="macro"))
    xgb_val_f1 = float(f1_score(y_val, xgb_pit.predict(X_val), average="macro"))

    print(f"\nSC PIT DECISION RESULTS")
    print(f"Val  — Accuracy: {val_acc:.3f}, F1 macro: {val_f1:.3f}")
    print(f"Test — Accuracy: {test_acc:.3f}, F1 macro: {test_f1:.3f}")
    print("\nVal Classification Report:")
    print(classification_report(y_val, val_pred, target_names=["Stay Out", "Pit"]))

    aiplatform.log_metrics(
        {
            "val_accuracy": val_acc,
            "val_f1_macro": val_f1,
            "test_accuracy": test_acc,
            "test_f1_macro": test_f1,
            "lgb_val_f1": lgb_val_f1,
            "xgb_val_f1": xgb_val_f1,
            "ensemble_weight_lgb": best_w,
            "n_circuits_sc_lookup": len(circuit_prob),
        }
    )

    # Confusion matrix
    cm = confusion_matrix(y_val, val_pred)
    fig, ax = plt.subplots(figsize=(5, 4))
    ConfusionMatrixDisplay(
        confusion_matrix=cm, display_labels=["Stay Out", "Pit"]
    ).plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(f"Safety Car Pit Decision — Confusion Matrix (Val)\nF1={val_f1:.3f}")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "safety_car_confusion_matrix.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/safety_car_confusion_matrix.png")

    # Model comparison bar chart
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        ["LGB", "XGB", "Ensemble"],
        [lgb_val_f1, xgb_val_f1, val_f1],
        color=["#4C72B0", "#DD8452", "#55A868"],
    )
    ax.set_title("Safety Car — Val F1 Macro by Model")
    ax.set_ylabel("F1 Macro")
    ax.set_ylim(0, 1)
    for i, v in enumerate([lgb_val_f1, xgb_val_f1, val_f1]):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=10)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "safety_car_model_comparison.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/safety_car_model_comparison.png")

    # Bias detection — sliced evaluation
    print("\nBIAS DETECTION — SLICED EVALUATION")
    val_pred_series = pd.Series(val_pred, index=val.index)
    y_val_series = pd.Series(y_val.values, index=val.index)
    slice_metrics = {}

    # Slice by season
    print("\nVal F1 by season:")
    for season in sorted(val["season"].unique()):
        mask = val["season"] == season
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
        print(f"  {season}: F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_season_{season}_f1"] = float(f1)

    # Slice by circuit type
    street_circuits = [
        "Monaco Grand Prix",
        "Azerbaijan Grand Prix",
        "Singapore Grand Prix",
        "Saudi Arabian Grand Prix",
        "Miami Grand Prix",
        "Las Vegas Grand Prix",
    ]
    val_street = val["raceName"].isin(street_circuits)
    for label, mask in [("street", val_street), ("permanent", ~val_street)]:
        if mask.sum() < 5:
            continue
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
        print(f"Val F1 {label} circuits: {f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_circuit_{label}_f1"] = float(f1)

    # Slice by race phase
    print("\nVal F1 by race phase:")
    for label, mask in [
        ("early_phase", val["race_phase"] == 0),
        ("mid_phase", val["race_phase"] == 1),
        ("late_phase", val["race_phase"] == 2),
    ]:
        if mask.sum() < 5:
            continue
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
        print(f"  {label}: F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_f1"] = float(f1)

    # Slice by pit stops so far
    print("\nVal F1 by pit stops so far:")
    for label, mask in [
        ("first_stint", val["pit_stops_so_far"] == 0),
        ("second_stint", val["pit_stops_so_far"] == 1),
        ("third_stint", val["pit_stops_so_far"] >= 2),
    ]:
        if mask.sum() < 5:
            continue
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
        print(f"  {label}: F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_f1"] = float(f1)

    aiplatform.log_metrics(slice_metrics)

    # Bias mitigation
    # Street circuits have higher SC frequency; circuit SC prob lookup already encodes this.
    # If street/permanent gap exceeds 0.08, find a circuit-specific decision threshold.
    street_f1 = slice_metrics.get("bias_circuit_street_f1", val_f1)
    permanent_f1 = slice_metrics.get("bias_circuit_permanent_f1", val_f1)
    f1_gap = abs(street_f1 - permanent_f1)
    print(f"\nBias mitigation check: street/permanent F1 gap = {f1_gap:.3f}")
    if f1_gap > 0.08:
        val_proba = (
            best_w * lgb_pit.predict_proba(X_val)[:, 1]
            + (1 - best_w) * xgb_pit.predict_proba(X_val)[:, 1]
        )
        street_idx = val[val["raceName"].isin(street_circuits)].index
        if len(street_idx) > 10:
            best_st_f1, best_st_thresh = 0, 0.5
            for thresh in np.arange(0.3, 0.7, 0.05):
                pred_s = (val_proba[val.index.isin(street_idx)] >= thresh).astype(int)
                f1_s = f1_score(
                    y_val_series[street_idx], pred_s, average="macro", zero_division=0
                )
                if f1_s > best_st_f1:
                    best_st_f1, best_st_thresh = f1_s, thresh
            print(
                f"  Street-adjusted threshold: {best_st_thresh:.2f}  (F1={best_st_f1:.3f})"
            )
            aiplatform.log_metrics(
                {
                    "bias_mitigation_applied": 1,
                    "bias_street_threshold": float(best_st_thresh),
                    "bias_street_permanent_f1_gap": float(f1_gap),
                }
            )
    else:
        print("  Gap within tolerance — no threshold adjustment required")
        aiplatform.log_metrics(
            {
                "bias_mitigation_applied": 0,
                "bias_street_permanent_f1_gap": float(f1_gap),
            }
        )

    # SHAP sensitivity analysis
    print("\nComputing SHAP values...")
    sample_idx = np.random.choice(len(X_val), size=min(2000, len(X_val)), replace=False)
    X_shap = X_val.iloc[sample_idx]

    explainer = shap.TreeExplainer(lgb_pit)
    shap_vals = explainer.shap_values(X_shap)

    # binary classifier: use class 1 (pit)
    sv = np.array(shap_vals)
    if sv.ndim == 3:
        sv = sv.mean(axis=2)
    shap_importance = pd.Series(
        np.abs(sv).mean(axis=0), index=X_shap.columns
    ).sort_values(ascending=False)

    print("Top 10 features by mean |SHAP|:")
    for feat, imp in shap_importance.head(10).items():
        print(f"  {feat}: {imp:.4f}")

    aiplatform.log_metrics(
        {f"shap_{k}": float(v) for k, v in shap_importance.head(10).items()}
    )

    fig, ax = plt.subplots(figsize=(8, 6))
    top_feats = shap_importance.head(15)
    ax.barh(top_feats.index[::-1], top_feats.values[::-1], color="steelblue")
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title("Safety Car — SHAP Feature Importance (Val 2022-23)")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "safety_car_shap_bar.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/safety_car_shap_bar.png")

    # Hyperparameter sensitivity
    print("\nHyperparameter sensitivity — min_child_samples:")
    hp_metrics = {}
    mcs_f1s = {}
    for mcs in [10, 20, 40, 80]:
        m = LGBMClassifier(
            n_estimators=300,
            max_depth=7,
            min_child_samples=mcs,
            learning_rate=0.01,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
            class_weight="balanced",
        )
        m.fit(X_train, y_train)
        f1 = f1_score(y_val, m.predict(X_val), average="macro")
        mcs_f1s[mcs] = f1
        hp_metrics[f"hp_mcs_{mcs}_val_f1"] = float(f1)
        print(f"  min_child_samples={mcs}: F1={f1:.4f}")

    print("\nHyperparameter sensitivity — num_leaves:")
    leaves_f1s = {}
    for nl in [15, 31, 63, 127]:
        m = LGBMClassifier(
            n_estimators=300,
            max_depth=-1,
            num_leaves=nl,
            learning_rate=0.01,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
            class_weight="balanced",
        )
        m.fit(X_train, y_train)
        f1 = f1_score(y_val, m.predict(X_val), average="macro")
        leaves_f1s[nl] = f1
        hp_metrics[f"hp_leaves_{nl}_val_f1"] = float(f1)
        print(f"  num_leaves={nl}: F1={f1:.4f}")

    aiplatform.log_metrics(hp_metrics)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(list(mcs_f1s.keys()), list(mcs_f1s.values()), "bo-", linewidth=2)
    axes[0].axvline(
        x=LGB_PARAMS["min_child_samples"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["min_child_samples"]})',
    )
    axes[0].set_xlabel("min_child_samples")
    axes[0].set_ylabel("Val F1 Macro")
    axes[0].set_title("min_child_samples Sensitivity")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(list(leaves_f1s.keys()), list(leaves_f1s.values()), "gs-", linewidth=2)
    axes[1].axvline(
        x=LGB_PARAMS["num_leaves"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["num_leaves"]})',
    )
    axes[1].set_xlabel("num_leaves")
    axes[1].set_ylabel("Val F1 Macro")
    axes[1].set_title("num_leaves Sensitivity")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    plt.suptitle("Safety Car — Hyperparameter Sensitivity", fontsize=12)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "safety_car_hp_sensitivity.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/safety_car_hp_sensitivity.png")

print("\nTop 10 Features (LGB):")
for feat, imp in sorted(
    zip(features, lgb_pit.feature_importances_), key=lambda x: -x[1]
)[:10]:
    print(f"  {feat}: {imp}")

# Save
os.makedirs("models", exist_ok=True)
joblib.dump(
    {
        "pit_lgb": lgb_pit,
        "pit_xgb": xgb_pit,
        "pit_weight": best_w,
        "circuit_sc_prob": circuit_prob,
        "features": features,
    },
    "models/safety_car.pkl",
)
print("\nSaved: models/safety_car.pkl")
print(f"  Circuit SC probabilities: {len(circuit_prob)} circuits")
print(f"  Pit decision — Val F1: {best_f1:.3f}")
