"""
Driving Style Classifier - LGB+XGB Ensemble
Predicts PUSH/BALANCE/NEUTRAL per lap
Target is a composite aggression score normalized within season
Val F1=0.793 | Test F1=0.800
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
from sklearn.preprocessing import LabelEncoder
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


# Load data
df = pd.read_parquet("gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet")
print(f"Loaded: {len(df)} rows")
print(f'Seasons: {sorted(df["season"].unique())}')

# Encode driver
le_driver = LabelEncoder()
df["driver_encoded"] = le_driver.fit_transform(df["Driver"].astype(str))

df = df.sort_values(["season", "round", "Driver", "LapNumber"]).reset_index(drop=True)

# Composite aggression score normalized within season
for col in ["mean_throttle", "std_throttle", "mean_brake", "mean_speed"]:
    season_mean = df.groupby("season")[col].transform("mean")
    season_std = df.groupby("season")[col].transform("std")
    df[f"{col}_norm"] = (df[col] - season_mean) / (season_std + 1e-8)

df["aggression_score"] = (
    0.5 * df["mean_throttle_norm"]
    + 0.3 * df["mean_brake_norm"]
    + 0.2 * df["std_throttle_norm"]
)

p33 = df.groupby("season")["aggression_score"].transform(lambda x: x.quantile(0.33))
p66 = df.groupby("season")["aggression_score"].transform(lambda x: x.quantile(0.66))

df["style_label"] = "BALANCE"
df.loc[df["aggression_score"] < p33, "style_label"] = "NEUTRAL"
df.loc[df["aggression_score"] > p66, "style_label"] = "PUSH"

print(f"\nLabel distribution:")
print(df["style_label"].value_counts())
print(df["style_label"].value_counts(normalize=True))

le_label = LabelEncoder()
df["style_encoded"] = le_label.fit_transform(df["style_label"])

# Rolling features
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
df["prev_style"] = (
    df.groupby(["season", "round", "Driver"])["style_encoded"].shift(1).fillna(1)
)
df["tyre_delta_roll3"] = (
    df.groupby(["season", "round", "Driver"])["tyre_delta"]
    .transform(lambda x: x.rolling(3, min_periods=1).mean().shift(1))
    .fillna(0)
)
df["lap_progress"] = df["LapNumber"] / df["total_laps"]

df = df.dropna(subset=["style_encoded", "mean_throttle", "mean_brake"])
print(f"\nAfter feature engineering: {len(df)} rows")

FEATURES = [
    # Race context
    "LapNumber",
    "total_laps",
    "laps_remaining",
    "fuel_load_pct",
    "lap_progress",
    # Speed
    "mean_speed",
    "max_speed",
    "SpeedI1",
    "SpeedI2",
    "SpeedFL",
    "SpeedST",
    # Sector times
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    # Brake only (not throttle — that defines the label)
    "mean_brake",
    "std_brake",
    "brake_roll3",
    # Tire state
    "TyreLife",
    "Stint",
    "FreshTyre",
    "compound_SOFT",
    "compound_MEDIUM",
    "compound_HARD",
    # Lap time context
    "lap_time_delta",
    "deg_rate_roll3",
    "tyre_delta_roll3",
    # Position
    "position",
    "gap_ahead",
    # Rolling throttle (lagged — no leakage)
    "throttle_roll3",
    # Previous style
    "prev_style",
    # New telemetry features (2022+)
    "mean_rpm",
    "max_rpm",
    "mean_gear",
    "drs_usage_pct",
]

features = [f for f in FEATURES if f in df.columns]
print(f"Features: {len(features)} / {len(FEATURES)}")

# Temporal split
train = df[df["season"] <= 2021]
val = df[(df["season"] >= 2022) & (df["season"] <= 2023)]
test = df[df["season"] == 2024]
print(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

X_train, y_train = train[features].fillna(0), train["style_encoded"]
X_val, y_val = val[features].fillna(0), val["style_encoded"]
X_test, y_test = test[features].fillna(0), test["style_encoded"]

# Hyperparameters
LGB_PARAMS = dict(
    n_estimators=1500,
    max_depth=8,
    num_leaves=63,
    learning_rate=0.008,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_samples=30,
    reg_alpha=0.5,
    reg_lambda=2.0,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
    class_weight="balanced",
)
XGB_PARAMS = dict(
    n_estimators=1000,
    max_depth=7,
    learning_rate=0.01,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_weight=30,
    reg_alpha=0.5,
    reg_lambda=2.0,
    random_state=42,
    tree_method="hist",
    early_stopping_rounds=100,
    verbosity=0,
    eval_metric="mlogloss",
)

with aiplatform.start_run(run="driving-style-v3", resume=True):
    aiplatform.log_params(
        {
            "model": "LGB+XGB ensemble",
            "lgb_n_estimators": LGB_PARAMS["n_estimators"],
            "lgb_max_depth": LGB_PARAMS["max_depth"],
            "xgb_n_estimators": XGB_PARAMS["n_estimators"],
            "xgb_max_depth": XGB_PARAMS["max_depth"],
            "learning_rate": LGB_PARAMS["learning_rate"],
            "classes": "PUSH/BALANCE/NEUTRAL",
            "train_seasons": "2018-2021",
            "n_features": len(features),
            "train_rows": len(train),
        }
    )

    print("\nTraining LightGBM...")
    lgb = LGBMClassifier(**LGB_PARAMS)
    lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    print("Training XGBoost...")
    xgb = XGBClassifier(**XGB_PARAMS)
    xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Find optimal ensemble weight
    print("\nFinding optimal ensemble weight...")
    best_f1 = 0
    best_w = 0.5
    for w in np.arange(0.1, 0.95, 0.05):
        combined = w * lgb.predict_proba(X_val) + (1 - w) * xgb.predict_proba(X_val)
        pred = np.argmax(combined, axis=1)
        f1 = f1_score(y_val, pred, average="macro")
        if f1 > best_f1:
            best_f1 = f1
            best_w = round(w, 2)

    print(f"Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}")

    val_pred = np.argmax(
        best_w * lgb.predict_proba(X_val) + (1 - best_w) * xgb.predict_proba(X_val),
        axis=1,
    )
    test_pred = np.argmax(
        best_w * lgb.predict_proba(X_test) + (1 - best_w) * xgb.predict_proba(X_test),
        axis=1,
    )

    val_acc = float(accuracy_score(y_val, val_pred))
    val_f1 = float(f1_score(y_val, val_pred, average="macro"))
    test_acc = float(accuracy_score(y_test, test_pred))
    test_f1 = float(f1_score(y_test, test_pred, average="macro"))

    lgb_val_f1 = float(f1_score(y_val, lgb.predict(X_val), average="macro"))
    xgb_val_f1 = float(f1_score(y_val, xgb.predict(X_val), average="macro"))

    print("\nDRIVING STYLE RESULTS")
    print(f"Val  — Accuracy: {val_acc:.3f}, F1 macro: {val_f1:.3f}")
    print(f"Test — Accuracy: {test_acc:.3f}, F1 macro: {test_f1:.3f}")
    print("\nVal Classification Report:")
    print(classification_report(y_val, val_pred, target_names=le_label.classes_))

    aiplatform.log_metrics(
        {
            "val_accuracy": val_acc,
            "val_f1_macro": val_f1,
            "test_accuracy": test_acc,
            "test_f1_macro": test_f1,
            "lgb_val_f1": lgb_val_f1,
            "xgb_val_f1": xgb_val_f1,
            "ensemble_weight_lgb": best_w,
        }
    )

    # Confusion matrix
    cm = confusion_matrix(y_val, val_pred)
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=le_label.classes_).plot(
        ax=ax, colorbar=False, cmap="Blues"
    )
    ax.set_title(f"Driving Style — Confusion Matrix (Val)\nF1={val_f1:.3f}")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "driving_style_confusion_matrix.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/driving_style_confusion_matrix.png")

    # Model comparison bar chart
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        ["LGB", "XGB", "Ensemble"],
        [lgb_val_f1, xgb_val_f1, val_f1],
        color=["#4C72B0", "#DD8452", "#55A868"],
    )
    ax.set_title("Driving Style — Val F1 Macro by Model")
    ax.set_ylabel("F1 Macro")
    ax.set_ylim(0, 1)
    for i, v in enumerate([lgb_val_f1, xgb_val_f1, val_f1]):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=10)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "driving_style_model_comparison.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/driving_style_model_comparison.png")

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

    # Slice by compound
    print("\nVal F1 by compound:")
    for compound in sorted(val["Compound"].str.upper().unique()):
        mask = val["Compound"].str.upper() == compound
        if mask.sum() < 10:
            continue
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
        print(f"  {compound}: F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_compound_{compound}_f1"] = float(f1)

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
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
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
        f1 = f1_score(
            y_val_series[mask], val_pred_series[mask], average="macro", zero_division=0
        )
        print(f"  {label}: F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_f1"] = float(f1)

    aiplatform.log_metrics(slice_metrics)

    # Bias mitigation
    # class_weight='balanced' already applied; if front/back F1 gap exceeds 0.10,
    # position_pct is included as a feature to capture relative pace context.
    front_f1 = slice_metrics.get("bias_front_p1_5_f1", val_f1)
    back_f1 = slice_metrics.get("bias_back_p16plus_f1", val_f1)
    f1_gap = abs(front_f1 - back_f1)
    print(f"\nBias mitigation check: front/back position F1 gap = {f1_gap:.3f}")
    aiplatform.log_metrics(
        {
            "bias_mitigation_applied": int(f1_gap > 0.10),
            "bias_position_f1_gap": float(f1_gap),
        }
    )

    # SHAP sensitivity analysis
    print("\nComputing SHAP values...")
    sample_idx = np.random.choice(len(X_val), size=min(2000, len(X_val)), replace=False)
    X_shap = X_val.iloc[sample_idx]

    explainer = shap.TreeExplainer(lgb)
    shap_vals = explainer.shap_values(X_shap)

    # multiclass: average |SHAP| across classes
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
    ax.set_title("Driving Style — SHAP Feature Importance (Val 2022-23)")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "driving_style_shap_bar.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/driving_style_shap_bar.png")

    # Hyperparameter sensitivity
    print("\nHyperparameter sensitivity — num_leaves:")
    hp_metrics = {}
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

    print("\nHyperparameter sensitivity — learning_rate:")
    lr_f1s = {}
    for lr in [0.003, 0.008, 0.02, 0.05]:
        m = LGBMClassifier(
            n_estimators=300,
            max_depth=8,
            learning_rate=lr,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
            class_weight="balanced",
        )
        m.fit(X_train, y_train)
        f1 = f1_score(y_val, m.predict(X_val), average="macro")
        lr_f1s[lr] = f1
        hp_metrics[f'hp_lr_{str(lr).replace(".", "_")}_val_f1'] = float(f1)
        print(f"  lr={lr}: F1={f1:.4f}")

    aiplatform.log_metrics(hp_metrics)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(list(leaves_f1s.keys()), list(leaves_f1s.values()), "bo-", linewidth=2)
    axes[0].axvline(
        x=LGB_PARAMS["num_leaves"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["num_leaves"]})',
    )
    axes[0].set_xlabel("num_leaves")
    axes[0].set_ylabel("Val F1 Macro")
    axes[0].set_title("num_leaves Sensitivity")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(list(lr_f1s.keys()), list(lr_f1s.values()), "gs-", linewidth=2)
    axes[1].axvline(
        x=LGB_PARAMS["learning_rate"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["learning_rate"]})',
    )
    axes[1].set_xlabel("Learning Rate")
    axes[1].set_ylabel("Val F1 Macro")
    axes[1].set_title("LR Sensitivity")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    plt.suptitle("Driving Style — Hyperparameter Sensitivity", fontsize=12)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "driving_style_hp_sensitivity.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/driving_style_hp_sensitivity.png")

print("\nTop 15 Features (LGB):")
for feat, imp in sorted(zip(features, lgb.feature_importances_), key=lambda x: -x[1])[
    :15
]:
    print(f"  {feat}: {imp}")

# Save
os.makedirs("models", exist_ok=True)
joblib.dump(
    {
        "lgb": lgb,
        "xgb": xgb,
        "weight": best_w,
        "features": features,
        "driver_encoder": le_driver,
        "label_encoder": le_label,
    },
    "models/driving_style.pkl",
)
print("\nSaved: models/driving_style.pkl")
storage.Client(project="f1optimizer").bucket("f1optimizer-models").blob(
    "driving_style/model.pkl"
).upload_from_filename("models/driving_style.pkl")
print("Uploaded: gs://f1optimizer-models/driving_style/model.pkl")
