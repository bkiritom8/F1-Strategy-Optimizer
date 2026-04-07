"""
Race Outcome Model - CatBoost + LightGBM Ensemble
Predicts finish tier: Podium / Points / Outside Points
Pre-race features only — no leakage
Championship points features from race_results.parquet
Val Acc=0.633 F1=0.630 | Test Acc=0.790 F1=0.778
"""

import ast
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
)
from sklearn.preprocessing import LabelEncoder
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
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


def extract_id(s, key):
    try:
        d = ast.literal_eval(str(s))
        return d[key] if isinstance(d, dict) else str(s)
    except Exception:
        return str(s)


# Load main features
df = pd.read_parquet(
    "gs://f1optimizer-data-lake/ml_features/race_results_features.parquet"
)
print(f"Loaded: {len(df)} rows")

df = df[df["season"] >= 2000].copy()
print(f"After 2000+ filter: {len(df)} rows")

df["position"] = pd.to_numeric(df["position"], errors="coerce")
df["grid"] = pd.to_numeric(df["grid"], errors="coerce").fillna(0)
df = df.dropna(subset=["position", "grid"])
df = df.sort_values(["season", "round", "grid"]).reset_index(drop=True)

df["driverId"] = df["driver"].apply(lambda x: extract_id(x, "driverId"))
df["constructorId"] = df["constructor"].apply(lambda x: extract_id(x, "constructorId"))
print(f'Sample driverId: {df["driverId"].head(3).tolist()}')

# 3-class target
df["finish_tier"] = pd.cut(
    df["position"], bins=[0, 3, 10, 100], labels=["Podium", "Points", "Outside"]
).astype(str)

print(f"\nFinish tier distribution:")
print(df["finish_tier"].value_counts())

# Championship points features from race_results.parquet
print("\nLoading race results for championship features...")
rr = pd.read_parquet("gs://f1optimizer-data-lake/processed/race_results.parquet")
rr["points"] = pd.to_numeric(rr["points"], errors="coerce").fillna(0)
rr["driverId_rr"] = rr["Driver"].apply(lambda x: extract_id(x, "driverId"))
rr["constructorId_rr"] = rr["Constructor"].apply(
    lambda x: extract_id(x, "constructorId")
)
rr = rr[rr["season"] >= 2000].sort_values(["season", "round"]).reset_index(drop=True)

# Cumulative points before each race — shift(1) per driver per season
rr["driver_cum_points"] = rr.groupby(["season", "driverId_rr"])["points"].transform(
    lambda x: x.shift(1).cumsum().fillna(0)
)
rr["constructor_cum_points"] = rr.groupby(["season", "constructorId_rr"])[
    "points"
].transform(lambda x: x.shift(1).cumsum().fillna(0))
rr["driver_champ_pos"] = rr.groupby(["season", "round"])["driver_cum_points"].rank(
    ascending=False, method="min"
)
rr["constructor_champ_pos"] = rr.groupby(["season", "round"])[
    "constructor_cum_points"
].rank(ascending=False, method="min")
rr["driver_points_last3"] = (
    rr.groupby(["season", "driverId_rr"])["points"]
    .transform(lambda x: x.shift(1).rolling(3, min_periods=1).sum())
    .fillna(0)
)

rr_features = rr[
    [
        "season",
        "round",
        "driverId_rr",
        "driver_cum_points",
        "driver_champ_pos",
        "constructor_cum_points",
        "constructor_champ_pos",
        "driver_points_last3",
    ]
].drop_duplicates(subset=["season", "round", "driverId_rr"])

df = df.merge(
    rr_features,
    left_on=["season", "round", "driverId"],
    right_on=["season", "round", "driverId_rr"],
    how="left",
)
df["driver_cum_points"] = df["driver_cum_points"].fillna(0)
df["driver_champ_pos"] = df["driver_champ_pos"].fillna(10)
df["constructor_cum_points"] = df["constructor_cum_points"].fillna(0)
df["constructor_champ_pos"] = df["constructor_champ_pos"].fillna(10)
df["driver_points_last3"] = df["driver_points_last3"].fillna(0)
print(f"After championship merge: {len(df)} rows")

# Rolling features — properly lagged, no leakage
ROLLING_WINDOW = 10
df["driver_rolling_avg_finish"] = (
    df.groupby("driverId")["position"]
    .transform(lambda s: s.shift(1).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(10.0)
)
df["constructor_rolling_avg_finish"] = (
    df.groupby("constructorId")["position"]
    .transform(lambda s: s.shift(1).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(10.0)
)
df["driver_season_avg_finish"] = (
    df.groupby(["driverId", "season"])["position"]
    .transform(lambda s: s.shift(1).expanding().mean())
    .fillna(10.0)
)
df["driver_rolling_podiums"] = (
    df.groupby("driverId")["position"]
    .transform(
        lambda s: (s.shift(1) <= 3).rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    .fillna(0.0)
)
df["constructor_rolling_podiums"] = (
    df.groupby("constructorId")["position"]
    .transform(
        lambda s: (s.shift(1) <= 3).rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    .fillna(0.0)
)
df["driver_rolling_points_finishes"] = (
    df.groupby("driverId")["position"]
    .transform(
        lambda s: (s.shift(1) <= 10).rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    .fillna(0.0)
)
df["grid_last"] = df.groupby("driverId")["grid"].shift(1).fillna(10.0)
df["grid_improvement"] = df["grid_last"] - df["grid"]

df = df.dropna(subset=["finish_tier"])
print(f"After feature engineering: {len(df)} rows")

# Temporal split
train = df[df["season"] <= 2021].copy()
val = df[df["season"].between(2022, 2023)].copy()
test = df[df["season"] == 2024].copy()
print(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

# Fit encoders on train only
le_driver = LabelEncoder()
le_constructor = LabelEncoder()
train["driver_enc"] = le_driver.fit_transform(train["driverId"])
train["constructor_enc"] = le_constructor.fit_transform(train["constructorId"])


def safe_encode(le, series):
    known = set(le.classes_)
    return series.apply(lambda v: le.transform([v])[0] if v in known else -1)


val["driver_enc"] = safe_encode(le_driver, val["driverId"])
val["constructor_enc"] = safe_encode(le_constructor, val["constructorId"])
test["driver_enc"] = safe_encode(le_driver, test["driverId"])
test["constructor_enc"] = safe_encode(le_constructor, test["constructorId"])

FEATURES = [
    # Pre-race features only — no position-derived features
    "grid",
    "grid_last",
    "grid_improvement",
    "driver_enc",
    "constructor_enc",
    "circuitId_encoded",
    "season",
    # Historical performance (properly lagged)
    "driver_rolling_avg_finish",
    "constructor_rolling_avg_finish",
    "driver_season_avg_finish",
    "driver_rolling_podiums",
    "constructor_rolling_podiums",
    "driver_rolling_points_finishes",
    # Championship standing going into race
    "driver_cum_points",
    "driver_champ_pos",
    "constructor_cum_points",
    "constructor_champ_pos",
    "driver_points_last3",
]

features = [f for f in FEATURES if f in train.columns]
print(f"Features: {len(features)} / {len(FEATURES)}")

X_train, y_train = train[features].fillna(0), train["finish_tier"]
X_val, y_val = val[features].fillna(0), val["finish_tier"]
X_test, y_test = test[features].fillna(0), test["finish_tier"]

print(f"\nVal class distribution:")
print(pd.Series(y_val).value_counts())

# Hyperparameters
CAT_PARAMS = dict(
    iterations=1000,
    depth=6,
    learning_rate=0.01,
    l2_leaf_reg=3.0,
    random_seed=42,
    loss_function="MultiClass",
    eval_metric="Accuracy",
    early_stopping_rounds=50,
    verbose=False,
    class_weights={"Podium": 3, "Points": 2, "Outside": 1},
)
LGB_PARAMS = dict(
    n_estimators=1000,
    max_depth=6,
    num_leaves=31,
    learning_rate=0.01,
    subsample=0.8,
    colsample_bytree=0.7,
    min_child_samples=20,
    reg_alpha=0.5,
    reg_lambda=1.0,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
    class_weight="balanced",
)

with aiplatform.start_run(run="race-outcome-v3", resume=True):
    aiplatform.log_params(
        {
            "model": "CatBoost+LGB ensemble",
            "target": "Podium/Points/Outside",
            "cat_iterations": CAT_PARAMS["iterations"],
            "cat_depth": CAT_PARAMS["depth"],
            "lgb_n_estimators": LGB_PARAMS["n_estimators"],
            "lgb_num_leaves": LGB_PARAMS["num_leaves"],
            "seasons_filter": "2000+",
            "train_seasons": "2000-2021",
            "n_features": len(features),
            "train_rows": len(train),
        }
    )

    print("\nTraining CatBoost...")
    cat_model = CatBoostClassifier(**CAT_PARAMS)
    cat_model.fit(X_train, y_train, eval_set=(X_val, y_val))

    print("Training LightGBM...")
    lgb_model = LGBMClassifier(**LGB_PARAMS)
    lgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    # Find optimal ensemble weight
    print("\nFinding optimal ensemble weight...")
    best_f1, best_w = 0, 0.5
    classes = cat_model.classes_
    lgb_classes = lgb_model.classes_

    for w in np.arange(0.1, 0.95, 0.05):
        cat_p = cat_model.predict_proba(X_val)
        lgb_p = lgb_model.predict_proba(X_val)
        lgb_aligned = np.zeros_like(cat_p)
        for i, c in enumerate(classes):
            if c in lgb_classes:
                lgb_aligned[:, i] = lgb_p[:, list(lgb_classes).index(c)]
        pred = classes[np.argmax(w * cat_p + (1 - w) * lgb_aligned, axis=1)]
        f1 = f1_score(y_val, pred, average="macro", zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_w = round(w, 2)

    def predict_ensemble(X):
        cat_p = cat_model.predict_proba(X)
        lgb_p = lgb_model.predict_proba(X)
        lgb_aligned = np.zeros_like(cat_p)
        for i, c in enumerate(classes):
            if c in lgb_classes:
                lgb_aligned[:, i] = lgb_p[:, list(lgb_classes).index(c)]
        return classes[np.argmax(best_w * cat_p + (1 - best_w) * lgb_aligned, axis=1)]

    val_pred = predict_ensemble(X_val)
    test_pred = predict_ensemble(X_test)

    val_acc = float(accuracy_score(y_val, val_pred))
    val_f1 = float(f1_score(y_val, val_pred, average="macro", zero_division=0))
    test_acc = float(accuracy_score(y_test, test_pred))
    test_f1 = float(f1_score(y_test, test_pred, average="macro", zero_division=0))

    cat_val_f1 = float(
        f1_score(y_val, cat_model.predict(X_val), average="macro", zero_division=0)
    )
    lgb_val_f1 = float(
        f1_score(y_val, lgb_model.predict(X_val), average="macro", zero_division=0)
    )

    print("\nRACE OUTCOME RESULTS")
    print(f"Val  — Accuracy: {val_acc:.3f}, F1 macro: {val_f1:.3f}")
    print(f"Test — Accuracy: {test_acc:.3f}, F1 macro: {test_f1:.3f}")
    print("\nIndividual models:")
    print(
        f"  CatBoost — Val Acc: {accuracy_score(y_val, cat_model.predict(X_val)):.3f}"
    )
    print(
        f"  LGB      — Val Acc: {accuracy_score(y_val, lgb_model.predict(X_val)):.3f}"
    )
    print("\nVal Classification Report:")
    print(classification_report(y_val, val_pred, zero_division=0))

    aiplatform.log_metrics(
        {
            "val_accuracy": val_acc,
            "val_f1_macro": val_f1,
            "test_accuracy": test_acc,
            "test_f1_macro": test_f1,
            "cat_val_f1": cat_val_f1,
            "lgb_val_f1": lgb_val_f1,
            "ensemble_weight_cat": best_w,
        }
    )

    # Confusion matrix
    label_order = ["Podium", "Points", "Outside"]
    cm = confusion_matrix(y_val, val_pred, labels=label_order)
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=label_order).plot(
        ax=ax, colorbar=False, cmap="Blues"
    )
    ax.set_title(f"Race Outcome — Confusion Matrix (Val)\nF1={val_f1:.3f}")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "race_outcome_confusion_matrix.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/race_outcome_confusion_matrix.png")

    # Model comparison bar chart
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        ["CatBoost", "LGB", "Ensemble"],
        [cat_val_f1, lgb_val_f1, val_f1],
        color=["#4C72B0", "#DD8452", "#55A868"],
    )
    ax.set_title("Race Outcome — Val F1 Macro by Model")
    ax.set_ylabel("F1 Macro")
    ax.set_ylim(0, 1)
    for i, v in enumerate([cat_val_f1, lgb_val_f1, val_f1]):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=10)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "race_outcome_model_comparison.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/race_outcome_model_comparison.png")

    # Bias detection — sliced evaluation
    print("\nBIAS DETECTION — SLICED EVALUATION")
    val_pred_series = pd.Series(val_pred, index=val.index)
    y_val_series = pd.Series(y_val.values, index=val.index)
    slice_metrics = {}

    # Slice by season
    print("\nVal Accuracy by season:")
    for season in sorted(val["season"].unique()):
        mask = val["season"] == season
        acc = float(accuracy_score(y_val_series[mask], val_pred_series[mask]))
        f1 = float(
            f1_score(
                y_val_series[mask],
                val_pred_series[mask],
                average="macro",
                zero_division=0,
            )
        )
        print(f"  {season}: Acc={acc:.3f}, F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_season_{season}_acc"] = acc
        slice_metrics[f"bias_season_{season}_f1"] = f1

    # Slice by constructor tier
    top_constructors = {"redbull", "mercedes", "ferrari", "mclaren"}
    mid_constructors = {
        "alpine",
        "astonmartin",
        "williams",
        "haas",
        "alfatauri",
        "alfaromeo",
    }
    val["constructor_tier"] = val["constructorId"].apply(
        lambda x: (
            "top"
            if x in top_constructors
            else ("mid" if x in mid_constructors else "back")
        )
    )
    print("\nVal Accuracy by constructor tier:")
    for tier in ["top", "mid", "back"]:
        mask = val["constructor_tier"] == tier
        if mask.sum() < 5:
            continue
        acc = float(accuracy_score(y_val_series[mask], val_pred_series[mask]))
        f1 = float(
            f1_score(
                y_val_series[mask],
                val_pred_series[mask],
                average="macro",
                zero_division=0,
            )
        )
        print(f"  {tier}: Acc={acc:.3f}, F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_constructor_{tier}_acc"] = acc
        slice_metrics[f"bias_constructor_{tier}_f1"] = f1

    # Slice by grid position tier
    print("\nVal Accuracy by grid tier:")
    for label, mask in [
        ("front_grid_1_5", val["grid"] <= 5),
        ("mid_grid_6_15", val["grid"].between(6, 15)),
        ("back_grid_16plus", val["grid"] > 15),
    ]:
        if mask.sum() < 5:
            continue
        acc = float(accuracy_score(y_val_series[mask], val_pred_series[mask]))
        f1 = float(
            f1_score(
                y_val_series[mask],
                val_pred_series[mask],
                average="macro",
                zero_division=0,
            )
        )
        print(f"  {label}: Acc={acc:.3f}, F1={f1:.3f}  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_acc"] = acc
        slice_metrics[f"bias_{label}_f1"] = f1

    aiplatform.log_metrics(slice_metrics)

    # Bias mitigation
    # Back-grid constructors have fewer training examples and higher variance.
    # class_weights={'Podium': 3, 'Points': 2, 'Outside': 1} applied in CatBoost.
    # If top/back constructor F1 gap exceeds 0.15, oversample back-constructor races on next run.
    top_f1 = slice_metrics.get("bias_constructor_top_f1", val_f1)
    back_f1 = slice_metrics.get("bias_constructor_back_f1", val_f1)
    f1_gap = abs(top_f1 - back_f1)
    print(f"\nBias mitigation check: top/back constructor F1 gap = {f1_gap:.3f}")
    if f1_gap > 0.15:
        back_count = (
            train["constructorId"].apply(
                lambda x: x not in top_constructors and x not in mid_constructors
            )
        ).sum()
        top_count = train["constructorId"].isin(top_constructors).sum()
        oversample_factor = max(1, top_count // max(back_count, 1))
        print(
            f"  Suggested oversample factor for back constructors: {oversample_factor}x"
        )
        aiplatform.log_metrics(
            {
                "bias_mitigation_applied": 1,
                "bias_constructor_f1_gap": float(f1_gap),
                "bias_oversample_factor": float(oversample_factor),
            }
        )
    else:
        print("  Gap within tolerance — no additional mitigation required")
        aiplatform.log_metrics(
            {"bias_mitigation_applied": 0, "bias_constructor_f1_gap": float(f1_gap)}
        )

    # SHAP sensitivity analysis
    print("\nComputing SHAP values...")
    sample_idx = np.random.choice(len(X_val), size=min(2000, len(X_val)), replace=False)
    X_shap = X_val.iloc[sample_idx]

    explainer = shap.TreeExplainer(lgb_model)
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
    ax.set_title("Race Outcome — SHAP Feature Importance (Val 2022-23)")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "race_outcome_shap_bar.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/race_outcome_shap_bar.png")

    # Hyperparameter sensitivity
    print("\nHyperparameter sensitivity — max_depth:")
    hp_metrics = {}
    depth_f1s = {}
    for md in [4, 6, 8, 10]:
        m = LGBMClassifier(
            n_estimators=300,
            max_depth=md,
            num_leaves=31,
            learning_rate=0.01,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
            class_weight="balanced",
        )
        m.fit(X_train, y_train)
        f1 = f1_score(y_val, m.predict(X_val), average="macro", zero_division=0)
        depth_f1s[md] = f1
        hp_metrics[f"hp_depth_{md}_val_f1"] = float(f1)
        print(f"  max_depth={md}: F1={f1:.4f}")

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
        f1 = f1_score(y_val, m.predict(X_val), average="macro", zero_division=0)
        leaves_f1s[nl] = f1
        hp_metrics[f"hp_leaves_{nl}_val_f1"] = float(f1)
        print(f"  num_leaves={nl}: F1={f1:.4f}")

    aiplatform.log_metrics(hp_metrics)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(list(depth_f1s.keys()), list(depth_f1s.values()), "bo-", linewidth=2)
    axes[0].axvline(
        x=LGB_PARAMS["max_depth"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["max_depth"]})',
    )
    axes[0].set_xlabel("max_depth")
    axes[0].set_ylabel("Val F1 Macro")
    axes[0].set_title("max_depth Sensitivity")
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
    plt.suptitle("Race Outcome — Hyperparameter Sensitivity", fontsize=12)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "race_outcome_hp_sensitivity.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/race_outcome_hp_sensitivity.png")

print("\nTop 10 features (LGB):")
for feat, imp in sorted(
    zip(features, lgb_model.feature_importances_), key=lambda x: -x[1]
)[:10]:
    print(f"  {feat}: {imp}")

# Save
os.makedirs("models", exist_ok=True)
joblib.dump(
    {
        "cat": cat_model,
        "lgb": lgb_model,
        "weight": best_w,
        "features": features,
        "driver_encoder": le_driver,
        "constructor_encoder": le_constructor,
        "classes": list(classes),
        "rolling_window": ROLLING_WINDOW,
    },
    "models/race_outcome.pkl",
)
print("\nSaved: models/race_outcome.pkl")
storage.Client(project="f1optimizer").bucket("f1optimizer-models").blob(
    "race_outcome/model.pkl"
).upload_from_filename("models/race_outcome.pkl")
print("Uploaded: gs://f1optimizer-models/race_outcome/model.pkl")

# ── Save feature distribution baseline for drift monitoring ──────────────────
from ml.monitoring.feature_stats import extract_feature_stats, save_to_gcs as save_stats  # noqa: E402
_train_stats = extract_feature_stats(X_train, features)
save_stats(_train_stats, "race_outcome")
print("Saved feature baseline for drift monitoring: race_outcome")
print("Uploaded: gs://f1optimizer-models/race_outcome/model.pkl")
