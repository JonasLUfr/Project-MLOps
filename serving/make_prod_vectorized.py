"""
Prereqs (from DataModeling.ipynb):
- artifacts/phishing_tfidf_logreg.joblib  (pipeline TF-IDF + LogisticRegression)
- artifacts/svd_ref.joblib                (TruncatedSVD fitted on the same TF-IDF space as ref_data.csv)

Usage (example):
    python scripts/make_prod_vectorized.py \
        --input data/prod_raw.csv \
        --text-col text \
        --output data/prod_data.csv

Input expectations:
- CSV with a text column (default: text)
- Optional target column (default: target). If absent, target is filled with NaN.

Output columns:
- svd_0 .. svd_199 : SVD-projected features
- prediction       : model class (0 safe / 1 phishing)
- proba_phishing   : model probability for class 1
- target           : user feedback/ground truth (if provided; else NaN)
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer


def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    return " ".join(s.split())  # collapse whitespace


def load_artifacts(artifact_dir: Path):
    model_path = artifact_dir / "phishing_tfidf_logreg.joblib"
    svd_path = artifact_dir / "svd_ref.joblib"

    if not model_path.exists():
        raise FileNotFoundError(f"Missing model artifact: {model_path}")
    if not svd_path.exists():
        raise FileNotFoundError(
            f"Missing SVD artifact: {svd_path}. Re-run DataModeling to save the fitted TruncatedSVD used for ref_data.csv."
        )

    pipeline: Pipeline = joblib.load(model_path)
    svd: TruncatedSVD = joblib.load(svd_path)

    tfidf: TfidfVectorizer = pipeline.named_steps.get("tfidf")
    if tfidf is None:
        raise ValueError("Loaded pipeline has no 'tfidf' step; expected the DataModeling pipeline.")

    return pipeline, tfidf, svd


def transform_and_predict(df: pd.DataFrame, pipeline, tfidf, svd, text_col: str, target_col: str):
    texts = df[text_col].apply(normalize_text).astype(str).str.slice(0, 10000)
    # Features for drift/monitoring
    tfidf_vec = tfidf.transform(texts)
    svd_vec = svd.transform(tfidf_vec)

    # Predictions using the full pipeline (tfidf + LR)
    preds = pipeline.predict(texts)
    proba = pipeline.predict_proba(texts)[:, 1] if hasattr(pipeline, "predict_proba") else np.zeros(len(preds))

    features = pd.DataFrame(svd_vec, columns=[f"svd_{i}" for i in range(svd_vec.shape[1])])
    out = features.copy()
    out["prediction"] = preds
    out["proba_phishing"] = proba

    # Map target labels to numeric (0/1)
    if target_col in df.columns:
        label_map = {
            "Phishing Email": 1,
            "Safe Email": 0,
        }
        out["target"] = df[target_col].map(label_map)
    else:
        out["target"] = np.nan

    return out


def main():
    parser = argparse.ArgumentParser(description="Vectorize prod emails with TF-IDF+SVD and add model predictions.")
    parser.add_argument("--input", required=True, help="Input CSV with raw emails")
    parser.add_argument("--output", required=True, help="Output CSV (prod_data.csv)")
    parser.add_argument("--text-col", default="text", help="Name of text column in input (default: text)")
    parser.add_argument("--target-col", default="target", help="Name of target/feedback column if present (default: target)")
    parser.add_argument("--artifact-dir", default="artifacts", help="Directory containing model + svd artifacts")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    artifact_dir = Path(args.artifact_dir)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = pd.read_csv(input_path)
    if args.text_col not in df.columns:
        raise ValueError(f"Text column '{args.text_col}' not found in {input_path}")

    pipeline, tfidf, svd = load_artifacts(artifact_dir)

    out = transform_and_predict(df, pipeline, tfidf, svd, args.text_col, args.target_col)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"Wrote {len(out)} rows to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)