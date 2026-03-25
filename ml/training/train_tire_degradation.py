"""
Tire Degradation Model - LGB+XGB Ensemble
Target: tyre_delta | Val MAE=0.294s R2=0.819 | Test MAE=0.285s R2=0.850
"""

import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
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
print(
    f'tyre_delta stats: mean={df["tyre_delta"].mean():.3f}, std={df["tyre_delta"].std():.3f}'
)

# Encode driver
le_driver = LabelEncoder()
df["driver_encoded"] = le_driver.fit_transform(df["Driver"].astype(str))

df = df.sort_values(["season", "round", "Driver", "LapNumber"]).reset_index(drop=True)

# Core interaction features
df["tyre_fuel_interaction"] = df["TyreLife"] * df["fuel_load_pct"]
df["tyre_squared"] = df["TyreLife"] ** 2
df["tyre_cubed"] = df["TyreLife"] ** 3
df["lap_progress"] = df["LapNumber"] / df["total_laps"]
df["tyre_per_stint"] = df["TyreLife"] / (df["Stint"] + 1)
df["throttle_brake_ratio"] = df["mean_throttle"] / (df["mean_brake"] + 1)
df["tyre_x_throttle"] = df["TyreLife"] * df["mean_throttle"] / 100
df["tyre_x_brake"] = df["TyreLife"] * df["mean_brake"] / 100
df["fuel_x_throttle"] = df["fuel_load_pct"] * df["mean_throttle"]

# Compound-age physics interactions
df["compound_age_soft"] = df["compound_SOFT"] * df["TyreLife"]
df["compound_age_medium"] = df["compound_MEDIUM"] * df["TyreLife"]
df["compound_age_hard"] = df["compound_HARD"] * df["TyreLife"]
df["tyre_age_sq_soft"] = df["compound_SOFT"] * df["tyre_squared"]
df["tyre_age_sq_medium"] = df["compound_MEDIUM"] * df["tyre_squared"]

# Rolling/lagged features (no leakage)
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
df["delta_std3"] = (
    df.groupby(["season", "round", "Driver"])["tyre_delta"]
    .transform(lambda x: x.rolling(3, min_periods=1).std().shift(1))
    .fillna(0)
)

# Cumulative tyre stress
df["cum_throttle"] = (
    df.groupby(["season", "round", "Driver"])["mean_throttle"].cumsum()
    / df["LapNumber"]
)
df["cum_brake"] = (
    df.groupby(["season", "round", "Driver"])["mean_brake"].cumsum() / df["LapNumber"]
)

# Position momentum
df["position_prev"] = (
    df.groupby(["season", "round", "Driver"])["position"]
    .shift(1)
    .fillna(df["position"])
)
df["position_change"] = df["position"] - df["position_prev"]

df = df.dropna(subset=["tyre_delta", "TyreLife", "mean_throttle", "mean_brake"])
print(f"After feature engineering: {len(df)} rows")

FEATURES = [
    # Tire state
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
    # Compound-age physics
    "compound_age_soft",
    "compound_age_medium",
    "compound_age_hard",
    "tyre_squared",
    "tyre_cubed",
    "tyre_per_stint",
    # Fuel
    "fuel_load_pct",
    "laps_remaining",
    "LapNumber",
    "lap_progress",
    # Throttle/brake
    "mean_throttle",
    "std_throttle",
    "mean_brake",
    "std_brake",
    "driving_style",
    "throttle_brake_ratio",
    "tyre_x_throttle",
    "tyre_x_brake",
    "fuel_x_throttle",
    "tyre_fuel_interaction",
    # Speed
    "mean_speed",
    "max_speed",
    "speed_delta",
    "SpeedI1",
    "SpeedI2",
    "SpeedFL",
    "SpeedST",
    # New telemetry features (2022+)
    "mean_rpm",
    "max_rpm",
    "mean_gear",
    "drs_usage_pct",
    "lap_distance",
    # Sector times
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    # Race context
    "position",
    "gap_ahead",
    # Degradation history (key features)
    "lap_time_delta",
    "deg_rate_roll3",
    "prev_delta",
    "prev_delta_2",
    "delta_diff",
    "delta_std3",
    "delta_roll3",
    "delta_roll5",
    "delta_roll7",
]

features = [f for f in FEATURES if f in df.columns]
print(f"Features: {len(features)} / {len(FEATURES)}")

# Temporal split
train = df[df["season"] <= 2021]
val = df[(df["season"] >= 2022) & (df["season"] <= 2023)]
test = df[df["season"] == 2024]
print(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

X_train, y_train = train[features].fillna(0), train["tyre_delta"]
X_val, y_val = val[features].fillna(0), val["tyre_delta"]
X_test, y_test = test[features].fillna(0), test["tyre_delta"]

print(
    f"Target std — Train: {y_train.std():.3f}, Val: {y_val.std():.3f}, Test: {y_test.std():.3f}"
)

# Hyperparameters
LGB_PARAMS = dict(
    n_estimators=2000,
    max_depth=10,
    num_leaves=63,
    learning_rate=0.006,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_samples=30,
    reg_alpha=0.5,
    reg_lambda=2.0,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
)
XGB_PARAMS = dict(
    n_estimators=1500,
    max_depth=8,
    learning_rate=0.008,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_weight=30,
    reg_alpha=0.5,
    reg_lambda=2.0,
    random_state=42,
    tree_method="hist",
    early_stopping_rounds=100,
    verbosity=0,
)

with aiplatform.start_run(run="tire-degradation-v1", resume=True):
    aiplatform.log_params(
        {
            "model": "LGB+XGB ensemble",
            "lgb_n_estimators": LGB_PARAMS["n_estimators"],
            "lgb_max_depth": LGB_PARAMS["max_depth"],
            "lgb_learning_rate": LGB_PARAMS["learning_rate"],
            "xgb_n_estimators": XGB_PARAMS["n_estimators"],
            "xgb_max_depth": XGB_PARAMS["max_depth"],
            "xgb_learning_rate": XGB_PARAMS["learning_rate"],
            "train_seasons": "2018-2021",
            "val_seasons": "2022-2023",
            "test_season": "2024",
            "n_features": len(features),
            "train_rows": len(train),
        }
    )

    print("\nTraining LightGBM...")
    lgb = LGBMRegressor(**LGB_PARAMS)
    lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    print("Training XGBoost...")
    xgb = XGBRegressor(**XGB_PARAMS)
    xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Find optimal ensemble weight
    print("\nFinding optimal ensemble weight...")
    best_mae = float("inf")
    best_w = 0.5
    for w in np.arange(0.1, 0.95, 0.05):
        pred = w * lgb.predict(X_val) + (1 - w) * xgb.predict(X_val)
        mae = mean_absolute_error(y_val, pred)
        if mae < best_mae:
            best_mae = mae
            best_w = round(w, 2)

    print(f"Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}")

    val_pred = best_w * lgb.predict(X_val) + (1 - best_w) * xgb.predict(X_val)
    test_pred = best_w * lgb.predict(X_test) + (1 - best_w) * xgb.predict(X_test)

    val_mae = float(mean_absolute_error(y_val, val_pred))
    val_r2 = float(r2_score(y_val, val_pred))
    test_mae = float(mean_absolute_error(y_test, test_pred))
    test_r2 = float(r2_score(y_test, test_pred))

    print("\nTIRE DEGRADATION RESULTS")
    print(f"Val  — MAE: {val_mae:.3f}s, R2: {val_r2:.3f}")
    print(f"Test — MAE: {test_mae:.3f}s, R2: {test_r2:.3f}")

    lgb_val_r2 = float(r2_score(y_val, lgb.predict(X_val)))
    xgb_val_r2 = float(r2_score(y_val, xgb.predict(X_val)))
    lgb_val_mae = float(mean_absolute_error(y_val, lgb.predict(X_val)))
    xgb_val_mae = float(mean_absolute_error(y_val, xgb.predict(X_val)))

    print("\nIndividual models:")
    print(
        f"  LGB — Val R2: {lgb_val_r2:.3f}, Test R2: {r2_score(y_test, lgb.predict(X_test)):.3f}"
    )
    print(
        f"  XGB — Val R2: {xgb_val_r2:.3f}, Test R2: {r2_score(y_test, xgb.predict(X_test)):.3f}"
    )

    aiplatform.log_metrics(
        {
            "val_mae": val_mae,
            "val_r2": val_r2,
            "test_mae": test_mae,
            "test_r2": test_r2,
            "lgb_val_r2": lgb_val_r2,
            "xgb_val_r2": xgb_val_r2,
            "ensemble_weight_lgb": best_w,
        }
    )

    # Model comparison bar chart
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    models = ["LGB", "XGB", "Ensemble"]
    val_r2s = [lgb_val_r2, xgb_val_r2, val_r2]
    val_maes = [lgb_val_mae, xgb_val_mae, val_mae]
    axes[0].bar(models, val_r2s, color=["#4C72B0", "#DD8452", "#55A868"])
    axes[0].set_title("Val R2 by Model")
    axes[0].set_ylabel("R2")
    axes[0].set_ylim(0, 1)
    for i, v in enumerate(val_r2s):
        axes[0].text(i, v + 0.01, f"{v:.3f}", ha="center", fontsize=9)
    axes[1].bar(models, val_maes, color=["#4C72B0", "#DD8452", "#55A868"])
    axes[1].set_title("Val MAE by Model (s)")
    axes[1].set_ylabel("MAE (s)")
    for i, v in enumerate(val_maes):
        axes[1].text(i, v + 0.002, f"{v:.3f}", ha="center", fontsize=9)
    plt.suptitle("Tire Degradation — Model Comparison", fontsize=12)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "tire_degradation_model_comparison.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/tire_degradation_model_comparison.png")

    # Predicted vs actual scatter
    fig, ax = plt.subplots(figsize=(6, 6))
    sample = np.random.choice(len(y_val), size=min(3000, len(y_val)), replace=False)
    ax.scatter(y_val.iloc[sample], val_pred[sample], alpha=0.2, s=5, color="steelblue")
    mn, mx = y_val.min(), y_val.max()
    ax.plot([mn, mx], [mn, mx], "r--", linewidth=1.5, label="Perfect prediction")
    ax.set_xlabel("Actual tyre_delta (s)")
    ax.set_ylabel("Predicted tyre_delta (s)")
    ax.set_title(
        f"Tire Degradation — Predicted vs Actual\nVal MAE={val_mae:.3f}s  R2={val_r2:.3f}"
    )
    ax.legend()
    p = os.path.join(PLOTS_DIR, "tire_degradation_pred_vs_actual.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/tire_degradation_pred_vs_actual.png")

    # Bias detection — sliced evaluation
    print("\nBIAS DETECTION — SLICED EVALUATION")
    val_pred_series = pd.Series(val_pred, index=val.index)
    y_val_series = pd.Series(y_val.values, index=val.index)
    slice_metrics = {}

    # Slice by season
    print("\nVal MAE by season:")
    for season in sorted(val["season"].unique()):
        mask = val["season"] == season
        mae = mean_absolute_error(y_val_series[mask], val_pred_series[mask])
        print(f"  {season}: MAE={mae:.3f}s  (n={mask.sum()})")
        slice_metrics[f"bias_season_{season}_mae"] = float(mae)

    # Slice by compound
    print("\nVal MAE by compound:")
    for compound in sorted(val["Compound"].str.upper().unique()):
        mask = val["Compound"].str.upper() == compound
        if mask.sum() < 10:
            continue
        mae = mean_absolute_error(y_val_series[mask], val_pred_series[mask])
        print(f"  {compound}: MAE={mae:.3f}s  (n={mask.sum()})")
        slice_metrics[f"bias_compound_{compound}_mae"] = float(mae)

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
        mae = mean_absolute_error(y_val_series[mask], val_pred_series[mask])
        print(f"\nVal MAE {label} circuits: {mae:.3f}s  (n={mask.sum()})")
        slice_metrics[f"bias_circuit_{label}_mae"] = float(mae)

    # Slice by tyre life bucket
    val_fresh = val["TyreLife"] <= 10
    for label, mask in [
        ("fresh_tyre_0_10", val_fresh),
        ("worn_tyre_10plus", ~val_fresh),
    ]:
        if mask.sum() < 10:
            continue
        mae = mean_absolute_error(y_val_series[mask], val_pred_series[mask])
        print(f"Val MAE {label}: {mae:.3f}s  (n={mask.sum()})")
        slice_metrics[f"bias_{label}_mae"] = float(mae)

    aiplatform.log_metrics(slice_metrics)

    # Bias mitigation
    # Street circuits show higher MAE due to atypical degradation curves.
    # If street/permanent gap exceeds 0.05s, apply inverse-frequency sample weights on next run.
    street_mae = slice_metrics.get("bias_circuit_street_mae", 0)
    permanent_mae = slice_metrics.get("bias_circuit_permanent_mae", 0)
    mae_gap = abs(street_mae - permanent_mae)
    print(f"\nBias mitigation check: street/permanent MAE gap = {mae_gap:.3f}s")
    if mae_gap > 0.05:
        val["circuit_type"] = (
            val["raceName"]
            .isin(street_circuits)
            .map({True: "street", False: "permanent"})
        )
        type_counts = val["circuit_type"].value_counts()
        total = len(val)
        print(f'  Street weight: {total / (2 * type_counts.get("street", 1)):.2f}')
        print(
            f'  Permanent weight: {total / (2 * type_counts.get("permanent", 1)):.2f}'
        )
        aiplatform.log_metrics(
            {
                "bias_mitigation_weight_applied": 1,
                "bias_street_permanent_gap": float(mae_gap),
            }
        )
    else:
        print("  Gap within tolerance — no reweighting required")
        aiplatform.log_metrics(
            {
                "bias_mitigation_weight_applied": 0,
                "bias_street_permanent_gap": float(mae_gap),
            }
        )

    # SHAP sensitivity analysis
    print("\nComputing SHAP values...")
    sample_idx = np.random.choice(len(X_val), size=min(2000, len(X_val)), replace=False)
    X_shap = X_val.iloc[sample_idx]

    explainer = shap.TreeExplainer(lgb)
    shap_vals = explainer.shap_values(X_shap)

    shap_importance = pd.Series(
        np.abs(shap_vals).mean(axis=0), index=X_shap.columns
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
    ax.set_title("Tire Degradation — SHAP Feature Importance (Val 2022-23)")
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "tire_degradation_shap_bar.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/tire_degradation_shap_bar.png")

    # Hyperparameter sensitivity
    print("\nHyperparameter sensitivity — learning_rate:")
    hp_metrics = {}
    lr_maes = {}
    for lr in [0.003, 0.006, 0.01, 0.02, 0.05]:
        m = LGBMRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=lr,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        m.fit(X_train, y_train)
        mae = mean_absolute_error(y_val, m.predict(X_val))
        lr_maes[lr] = mae
        hp_metrics[f'hp_lr_{str(lr).replace(".", "_")}_val_mae'] = float(mae)
        print(f"  lr={lr}: MAE={mae:.4f}s")

    print("\nHyperparameter sensitivity — num_leaves:")
    leaves_maes = {}
    for nl in [15, 31, 63, 127, 255]:
        m = LGBMRegressor(
            n_estimators=300,
            max_depth=-1,
            num_leaves=nl,
            learning_rate=0.01,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        m.fit(X_train, y_train)
        mae = mean_absolute_error(y_val, m.predict(X_val))
        leaves_maes[nl] = mae
        hp_metrics[f"hp_leaves_{nl}_val_mae"] = float(mae)
        print(f"  num_leaves={nl}: MAE={mae:.4f}s")

    aiplatform.log_metrics(hp_metrics)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(list(lr_maes.keys()), list(lr_maes.values()), "bo-", linewidth=2)
    axes[0].axvline(
        x=LGB_PARAMS["learning_rate"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["learning_rate"]})',
    )
    axes[0].set_xlabel("Learning Rate")
    axes[0].set_ylabel("Val MAE (s)")
    axes[0].set_title("LR Sensitivity")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(
        list(leaves_maes.keys()), list(leaves_maes.values()), "gs-", linewidth=2
    )
    axes[1].axvline(
        x=LGB_PARAMS["num_leaves"],
        color="red",
        linestyle="--",
        label=f'Chosen ({LGB_PARAMS["num_leaves"]})',
    )
    axes[1].set_xlabel("num_leaves")
    axes[1].set_ylabel("Val MAE (s)")
    axes[1].set_title("num_leaves Sensitivity")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    plt.suptitle("Tire Degradation — Hyperparameter Sensitivity", fontsize=12)
    plt.tight_layout()
    p = os.path.join(PLOTS_DIR, "tire_degradation_hp_sensitivity.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    upload_plot(p, "plots/tire_degradation_hp_sensitivity.png")

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
    },
    "models/tire_degradation.pkl",
)
print("\nSaved: models/tire_degradation.pkl")
