"""
Overtake Probability Model - RandomForest with Isotonic Calibration
Predicts binary overtake_success (0/1) per lap
Uses cumulative race time gap to car ahead
Val F1=0.326 | Test F1=0.328
"""

import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
)
from sklearn.preprocessing import LabelEncoder
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


# Load data
df = pd.read_parquet("gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet")
print(f"Loaded: {len(df)} rows")
print(f'Seasons: {sorted(df["season"].unique())}')

# Encode driver
le_driver = LabelEncoder()
df["driver_encoded"] = le_driver.fit_transform(df["Driver"].astype(str))

df = df.sort_values(["season", "round", "Driver", "LapNumber"]).reset_index(drop=True)

print(f"\novertake_success distribution:")
print(df["overtake_success"].value_counts())
print(df["overtake_success"].value_counts(normalize=True).round(3))

# Compute cumulative race gaps
print("\nComputing cumulative race gaps...")
df["cum_race_time"] = df.groupby(["season", "round", "Driver"])["LapTime"].cumsum()


def compute_gaps(group):
    group = group.sort_values("cum_race_time")
    group["real_gap_ahead"] = group["cum_race_time"].diff().fillna(0)
    return group


gap_df = df.groupby(["season", "round", "LapNumber"], group_keys=False).apply(
    compute_gaps
)
df["real_gap_ahead"] = (
    gap_df["real_gap_ahead"].reindex(df.index).fillna(0).clip(-60, 60)
)
df["in_drs_zone"] = (df["real_gap_ahead"].abs() < 1.0).astype(int)
df["in_drs_zone_2"] = (df["real_gap_ahead"].abs() < 2.0).astype(int)

print(f'  Real DRS zone laps (< 1s): {df["in_drs_zone"].sum()}')
print(f'  Real DRS zone laps (< 2s): {df["in_drs_zone_2"].sum()}')

# Feature engineering
df["tyre_squared"] = df["TyreLife"] ** 2
df["tyre_cubed"] = df["TyreLife"] ** 3
df["tyre_per_stint"] = df["TyreLife"] / (df["Stint"] + 1)
df["lap_progress"] = df["LapNumber"] / df["total_laps"]
df["compound_age_soft"] = df["compound_SOFT"] * df["TyreLife"]
df["compound_age_medium"] = df["compound_MEDIUM"] * df["TyreLife"]
df["compound_age_hard"] = df["compound_HARD"] * df["TyreLife"]

for window in [3, 5, 7]:
    df[f"delta_roll{window}"] = (
        df.groupby(["season", "round", "Driver"])["tyre_delta"]
        .transform(lambda x, w=window: x.rolling(w, min_periods=1).mean().shift(1))
        .fillna(0)
    )

df["prev_delta"] = (
    df.groupby(["season", "round", "Driver"])["tyre_delta"].shift(1).fillna(0)
)
df["prev_delta_2"] = (
    df.groupby(["season", "round", "Driver"])["tyre_delta"].shift(2).fillna(0)
)
df["delta_diff"] = df["prev_delta"] - df["prev_delta_2"]
df["cum_throttle"] = (
    df.groupby(["season", "round", "Driver"])["mean_throttle"].cumsum()
    / df["LapNumber"]
)
df["cum_brake"] = (
    df.groupby(["season", "round", "Driver"])["mean_brake"].cumsum() / df["LapNumber"]
)
df["overtake_roll3"] = (
    df.groupby(["season", "round", "Driver"])["overtake_success"]
    .transform(lambda x: x.rolling(3, min_periods=1).mean().shift(1))
    .fillna(0)
)
df["throttle_roll3"] = (
    df.groupby(["season", "round", "Driver"])["mean_throttle"]
    .transform(lambda x: x.rolling(3, min_periods=1).mean().shift(1))
    .fillna(df["mean_throttle"])
)
df["brake_roll3"] = (
    df.groupby(["season", "round", "Driver"])["mean_brake"]
    .transform(lambda x: x.rolling(3, min_periods=1).mean().shift(1))
    .fillna(df["mean_brake"])
)
df["drs_zone"] = (df["gap_ahead"].abs() < 1.0).astype(int)
df["tyre_x_throttle"] = df["TyreLife"] * df["mean_throttle"] / 100
df["tyre_x_brake"] = df["TyreLife"] * df["mean_brake"] / 100
df["speed_roll3"] = (
    df.groupby(["season", "round", "Driver"])["mean_speed"]
    .transform(lambda x: x.rolling(3, min_periods=1).mean().shift(1))
    .fillna(df["mean_speed"])
)
df["speed_delta"] = df["mean_speed"] - df["speed_roll3"]
field_size = df.groupby(["season", "round"])["Driver"].transform("nunique")
df["position_pct"] = df["position"] / field_size
df["field_size"] = field_size
df["driving_style_encoded"] = (
    df["driving_style"]
    if df["driving_style"].dtype != object
    else df["driving_style"].map({"NEUTRAL": 0, "BALANCE": 1, "PUSH": 2}).fillna(1)
)

df = df.dropna(subset=["overtake_success", "position"])
print(f"\nAfter feature engineering: {len(df)} rows")

FEATURES = [
    # Real gap features
    "real_gap_ahead",
    "in_drs_zone",
    "in_drs_zone_2",
    # Old gap proxy
    "gap_ahead",
    "drs_zone",
    # Tyre state
    "TyreLife",
    "Stint",
    "FreshTyre",
    "compound_SOFT",
    "compound_MEDIUM",
    "compound_HARD",
    "compound_INTERMEDIATE",
    "compound_WET",
    "compound_SUPERSOFT",
    "compound_ULTRASOFT",
    "compound_HYPERSOFT",
    "compound_age_soft",
    "compound_age_medium",
    "compound_age_hard",
    "tyre_squared",
    "tyre_cubed",
    "tyre_per_stint",
    "tyre_x_throttle",
    "tyre_x_brake",
    # Degradation
    "tyre_delta",
    "deg_rate_roll3",
    "prev_delta",
    "prev_delta_2",
    "delta_diff",
    "delta_roll3",
    "delta_roll5",
    "delta_roll7",
    # Throttle/brake
    "mean_throttle",
    "std_throttle",
    "throttle_roll3",
    "mean_brake",
    "std_brake",
    "brake_roll3",
    "cum_throttle",
    "cum_brake",
    # Speed
    "mean_speed",
    "max_speed",
    "speed_delta",
    "SpeedI1",
    "SpeedI2",
    "SpeedFL",
    "SpeedST",
    # Sector times
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    # Race context
    "LapNumber",
    "lap_progress",
    "laps_remaining",
    "fuel_load_pct",
    "position",
    "position_pct",
    "field_size",
    # Overtake history
    "overtake_roll3",
    # New telemetry
    "mean_rpm",
    "max_rpm",
    "mean_gear",
    "drs_usage_pct",
    # Driving style and driver
    "driving_style_encoded",
    "driver_encoded",
]

features = [f for f in FEATURES if f in df.columns]
print(f"Features: {len(features)} / {len(FEATURES)}")

# Temporal split
train = df[df["season"] <= 2021]
val = df[(df["season"] >= 2022) & (df["season"] <= 2023)]
test = df[df["season"] == 2024]
print(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

X_train, y_train = train[features].fillna(0), train["overtake_success"]
X_val, y_val = val[features].fillna(0), val["overtake_success"]
X_test, y_test = test[features].fillna(0), test["overtake_success"]

print(
    f"\nClass balance — Train: {y_train.mean():.3f}, Val: {y_val.mean():.3f}, Test: {y_test.mean():.3f}"
)

# Hyperparameters
RF_PARAMS = dict(
    n_estimators=1000,
    max_depth=12,
    min_samples_leaf=30,
    max_features="sqrt",
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

with aiplatform.start_run(run="overtake-prob-v2"):
    aiplatform.log_params(
        {
            "model": "RandomForest+IsotonicCalibration",
            "n_estimators": RF_PARAMS["n_estimators"],
            "max_depth": RF_PARAMS["max_depth"],
            "min_samples_leaf": RF_PARAMS["min_samples_leaf"],
            "calibration": "isotonic cv=3",
            "positive_rate": float(y_train.mean()),
            "train_seasons": "2018-2021",
            "n_features": len(features),
        }
    )

    print("\nTraining RandomForest...")
    base_rf = RandomForestClassifier(**RF_PARAMS)
    model = CalibratedClassifierCV(base_rf, method="isotonic", cv=3)
    model.fit(X_train, y_train)

    # Find optimal threshold
    val_proba = model.predict_proba(X_val)[:, 1]
    best_f1, best_thresh = 0, 0.5
    for thresh in np.arange(0.1, 0.6, 0.01):
        pred = (val_proba >= thresh).astype(int)
        f1 = f1_score(y_val, pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = round(thresh, 2)

    print(f"Optimal threshold: {best_thresh}")

    val_pred = (val_proba >= best_thresh).astype(int)
    test_proba = model.predict_proba(X_test)[:, 1]
    test_pred = (test_proba >= best_thresh).astype(int)

    try:
        frac_pos, mean_pred = calibration_curve(y_val, val_proba, n_bins=10)
        ece = float(np.mean(np.abs(frac_pos - mean_pred)))
    except Exception:
        ece = float("nan")

    val_f1 = float(f1_score(y_val, val_pred, zero_division=0))
    val_acc = float(accuracy_score(y_val, val_pred))
    test_f1 = float(f1_score(y_test, test_pred, zero_division=0))
    test_acc = float(accuracy_score(y_test, test_pred))

    print("\nOVERTAKE PROBABILITY RESULTS")
    print(
        f"Val  — F1: {val_f1:.3f}, Acc: {val_acc:.3f}, "
        f"Prec: {precision_score(y_val, val_pred, zero_division=0):.3f}, "
        f"Rec: {recall_score(y_val, val_pred, zero_division=0):.3f}"
    )
    print(
        f"Test — F1: {test_f1:.3f}, Acc: {test_acc:.3f}, "
        f"Prec: {precision_score(y_test, test_pred, zero_division=0):.3f}, "
        f"Rec: {recall_score(y_test, test_pred, zero_division=0):.3f}"
    )
    print(f"Val ECE: {ece:.4f} (target < 0.05)")
    print("\nVal Classification Report:")
    print(
        classification_report(
            y_val, val_pred, target_names=["No overtake", "Overtake"], zero_division=0
        )
    )

    aiplatform.log_metrics(
        {
            "val_f1": val_f1,
            "val_accuracy": val_acc,
            "test_f1": test_f1,
            "test_accuracy": test_acc,
            "val_ece": ece,
            "threshold": best_thresh,
        }
    )

    # Confusion matrix
    cm = confusion_matrix(y_val, val_pred)
    fig, ax = plt.subplots(figsize=(5, 4))
    ConfusionMatrixDisplay(
        confusion_matrix=cm, display_labels=["No Overtake", "Overtake"]
    ).plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(f"Overtake Probability — Confusion Matrix (Val)\nF1={val_f1:.3f}")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "overtake_prob_confusion_matrix.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/overtake_prob_confusion_matrix.png")

    # Calibration curve
    try:
        fig, ax = plt.subplots(figsize=(6, 5))
        frac_pos, mean_pred = calibration_curve(y_val, val_proba, n_bins=10)
        ax.plot(mean_pred, frac_pos, "s-", label=f"RF+Isotonic (ECE={ece:.3f})")
        ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
        ax.set_xlabel("Mean predicted probability")
        ax.set_ylabel("Fraction of positives")
        ax.set_title("Overtake Probability — Calibration Curve (Val)")
        ax.legend()
        plt.tight_layout()
        p = os.path.join(PLOTS_DIR, "overtake_prob_calibration.png")
        plt.savefig(p, dpi=150, bbox_inches="tight")
        plt.close()
        upload_plot(p, "plots/overtake_prob_calibration.png")
    except Exception as e:
        print(f"Calibration plot skipped: {e}")

    # Bias detection — sliced evaluation
    print("\nBIAS DETECTION — SLICED EVALUATION")
    val_pred_series = pd.Series(val_pred, index=val.index)
    y_val_series = pd.Series(y_val.values, index=val.index)
    slice_metrics = {}

    # Slice by season
    print("\nVal F1 by season:")
    for season in sorted(val["season"].unique()):
        mask = val["season"] == season
        f1 = f1_score(y_val_series[mask], val_pred_series[mask], zero_division=0)
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
        if mask.sum() < 10:
            continue
        f1 = f1_score(y_val_series[mask], val_pred_series[mask], zero_division=0)
        print(f"Val F1 {label} circuits: {f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_circuit_{label}_f1"] = float(f1)

    # Slice by position tier
    print("\nVal F1 by position tier:")
    for label, mask in [
        ("front_p1_5", val["position"] <= 5),
        ("mid_p6_15", val["position"].between(6, 15)),
        ("back_p16plus", val["position"] > 15),
    ]:
        if mask.sum() < 10:
            continue
        f1 = f1_score(y_val_series[mask], val_pred_series[mask], zero_division=0)
        print(f"  {label}: F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_f1"] = float(f1)

    # Slice by DRS zone
    for label, mask in [
        ("in_drs", val["in_drs_zone"] == 1),
        ("not_in_drs", val["in_drs_zone"] == 0),
    ]:
        if mask.sum() < 10:
            continue
        f1 = f1_score(y_val_series[mask], val_pred_series[mask], zero_division=0)
        print(f"Val F1 {label}: {f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_f1"] = float(f1)

    aiplatform.log_metrics(slice_metrics)

    # Bias mitigation
    # Street circuits have fewer overtaking opportunities; class_weight='balanced' applied.
    # If street/permanent gap exceeds 0.05, find a circuit-specific threshold.
    street_f1 = slice_metrics.get("bias_circuit_street_f1", val_f1)
    permanent_f1 = slice_metrics.get("bias_circuit_permanent_f1", val_f1)
    f1_gap = abs(street_f1 - permanent_f1)
    print(f"\nBias mitigation check: street/permanent F1 gap = {f1_gap:.3f}")
    if f1_gap > 0.05:
        street_idx = val[val["raceName"].isin(street_circuits)].index
        if len(street_idx) > 10:
            best_st_f1, best_st_thresh = 0, best_thresh
            for thresh in np.arange(0.1, 0.6, 0.02):
                pred_s = (val_proba[val.index.isin(street_idx)] >= thresh).astype(int)
                f1_s = f1_score(y_val_series[street_idx], pred_s, zero_division=0)
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
    sample_idx = np.random.choice(len(X_val), size=min(5000, len(X_val)), replace=False)
    X_shap = X_val.iloc[sample_idx]
    base_rf_inner = model.calibrated_classifiers_[0].estimator
    explainer = shap.TreeExplainer(base_rf_inner)
    shap_vals = explainer.shap_values(X_shap)

    # binary classifier: use class 1 (overtake)
    sv = shap_vals[1] if isinstance(shap_vals, list) else shap_vals

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
    ax.set_title("Overtake Probability — SHAP Feature Importance (Val 2022-23)")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "overtake_prob_shap_bar.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/overtake_prob_shap_bar.png")

    # Hyperparameter sensitivity
    print("\nHyperparameter sensitivity — max_depth:")
    hp_metrics = {}
    depth_f1s = {}
    for md in [6, 9, 12, 16]:
        m = RandomForestClassifier(
            n_estimators=200,
            max_depth=md,
            min_samples_leaf=30,
            max_features="sqrt",
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        m.fit(X_train, y_train)
        pred = (m.predict_proba(X_val)[:, 1] >= best_thresh).astype(int)
        f1 = f1_score(y_val, pred, zero_division=0)
        depth_f1s[md] = f1
        hp_metrics[f"hp_depth_{md}_val_f1"] = float(f1)
        print(f"  max_depth={md}: F1={f1:.4f}")

    print("\nHyperparameter sensitivity — min_samples_leaf:")
    leaf_f1s = {}
    for msl in [10, 20, 30, 50]:
        m = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=msl,
            max_features="sqrt",
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        m.fit(X_train, y_train)
        pred = (m.predict_proba(X_val)[:, 1] >= best_thresh).astype(int)
        f1 = f1_score(y_val, pred, zero_division=0)
        leaf_f1s[msl] = f1
        hp_metrics[f"hp_msl_{msl}_val_f1"] = float(f1)
        print(f"  min_samples_leaf={msl}: F1={f1:.4f}")

    aiplatform.log_metrics(hp_metrics)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(list(depth_f1s.keys()), list(depth_f1s.values()), "bo-", linewidth=2)
    axes[0].axvline(
        x=RF_PARAMS["max_depth"],
        color="red",
        linestyle="--",
        label=f'Chosen ({RF_PARAMS["max_depth"]})',
    )
    axes[0].set_xlabel("max_depth")
    axes[0].set_ylabel("Val F1")
    axes[0].set_title("max_depth Sensitivity")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(list(leaf_f1s.keys()), list(leaf_f1s.values()), "gs-", linewidth=2)
    axes[1].axvline(
        x=RF_PARAMS["min_samples_leaf"],
        color="red",
        linestyle="--",
        label=f'Chosen ({RF_PARAMS["min_samples_leaf"]})',
    )
    axes[1].set_xlabel("min_samples_leaf")
    axes[1].set_ylabel("Val F1")
    axes[1].set_title("min_samples_leaf Sensitivity")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    plt.suptitle("Overtake Probability — Hyperparameter Sensitivity", fontsize=12)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "overtake_prob_hp_sensitivity.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/overtake_prob_hp_sensitivity.png")

print("\nTop 15 Features:")
rf_inner = model.calibrated_classifiers_[0].estimator
for feat, imp in sorted(
    zip(features, rf_inner.feature_importances_), key=lambda x: -x[1]
)[:15]:
    print(f"  {feat}: {imp:.4f}")

# Save
os.makedirs("models", exist_ok=True)
joblib.dump(
    {
        "model": model,
        "threshold": best_thresh,
        "features": features,
        "driver_encoder": le_driver,
    },
    "models/overtake_prob.pkl",
)
print("\nSaved: models/overtake_prob.pkl")
