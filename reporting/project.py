import pandas as pd
import os
import time
import json
import joblib
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, ClassificationPreset, TargetDriftPreset
from evidently.metrics import DatasetSummaryMetric 
from evidently.ui.workspace import Workspace
from evidently.pipeline.column_mapping import ColumnMapping
from evidently.ui.dashboards import DashboardPanelCounter, PanelValue, ReportFilter, CounterAgg
from evidently.renderers.html_widgets import WidgetSize

# Path (pour docker)
REF_DATA_PATH = "/data/ref_data.csv"
PROD_RAW_PATH = "/data/prod_data_raw.csv"
PROD_VEC_PATH = "/data/prod_data.csv"
METRICS_PATH = "/artifacts/metrics.json"
ARTIFACTS_DIR = "/artifacts"
WORKSPACE_PATH = "workspace"

def load_metrics():
    """Charge les métriques (Accuracy, F1...) depuis metrics.json"""
    if os.path.exists(METRICS_PATH):
        try:
            with open(METRICS_PATH, 'r') as f:
                m = json.load(f)
            stats = m.get("test", m.get("val", {}))
            return stats
        except Exception as e:
            print(f"Erreur lecture metrics.json: {e}")
    return {}

def vectorize_prod_data():
    """Vectorisation"""
    if not os.path.exists(PROD_RAW_PATH):
        return False

    print("Début de la vectorisation...")
    try:
        svd_path = os.path.join(ARTIFACTS_DIR, "svd_ref.joblib")
        tfidf_path = os.path.join(ARTIFACTS_DIR, "tfidf_vectorizer.joblib")
        
        if not os.path.exists(svd_path) or not os.path.exists(tfidf_path):
            print("Artefacts manquants (SVD ou TFIDF).")
            return False

        # Chargement direct
        svd = joblib.load(svd_path)
        tfidf = joblib.load(tfidf_path)

        df_raw = pd.read_csv(PROD_RAW_PATH)
        if 'email_text' not in df_raw.columns:
            return False

        texts = df_raw['email_text'].fillna("").astype(str).tolist()
        
        # Transformation
        tfidf_vec = tfidf.transform(texts)
        svd_vec = svd.transform(tfidf_vec)

        # DataFrame SVD
        cols = [f"svd_{i}" for i in range(svd_vec.shape[1])]
        df_vec = pd.DataFrame(svd_vec, columns=cols)
        
        # Mapping Text -> Int
        label_map = {"Phishing Email": 1, "Safe Email": 0}
        
        if 'prediction' in df_raw.columns:
            df_vec['prediction'] = df_raw['prediction'].map(label_map).fillna(0).astype(int)
        if 'target' in df_raw.columns:
            df_vec['target'] = df_raw['target'].map(label_map).fillna(0).astype(int)

        df_vec.to_csv(PROD_VEC_PATH, index=False)
        print(f"prod_data.csv généré ({len(df_vec)} lignes).")
        return True

    except Exception as e:
        print(f"Erreur vectorisation: {e}")
        return False

def create_report():
    print("Lancement du reporting...")
    
    # Génération
    vectorize_prod_data()
    
    # Chargement
    if not os.path.exists(REF_DATA_PATH) or not os.path.exists(PROD_VEC_PATH):
        print("❌ Données manquantes.")
        return

    ref_data = pd.read_csv(REF_DATA_PATH)
    prod_data = pd.read_csv(PROD_VEC_PATH)
    
    # Nettoyage
    if 'prediction' in ref_data.columns:
        ref_data = ref_data.drop(columns=['prediction'])
    if 'prediction' in prod_data.columns:
        prod_data = prod_data.drop(columns=['prediction'])

    # Typage numérique forcé
    for col in ref_data.columns:
        if col.startswith('svd_'):
            ref_data[col] = pd.to_numeric(ref_data[col], errors='coerce')
            if col in prod_data.columns:
                prod_data[col] = pd.to_numeric(prod_data[col], errors='coerce')
    
    ref_data = ref_data.fillna(0)
    prod_data = prod_data.fillna(0)

    # Workspace
    ws = Workspace.create(WORKSPACE_PATH)
    project_name = "Phishing Monitor"
    search = ws.search_project(project_name)
    project = search[0] if search else ws.create_project(project_name)
    
    project.dashboard.panels = []
    
    metrics = load_metrics()
    acc = metrics.get('accuracy', 0) * 100
    
    # Panel 1: Accuracy (Statique)
    project.dashboard.add_panel(
        DashboardPanelCounter(
            title=f"Accuracy (Training): {acc:.1f}%",
            filter=ReportFilter(metadata_values={}, tag_values=[]),
            value=PanelValue(metric_id="DatasetSummaryMetric", field_path="current.number_of_columns", legend="Indicateur Fixe"),
            agg=CounterAgg.LAST,
            size=WidgetSize.HALF
        )
    )
    
    # Panel 2: Volumétrie (Dynamique)
    project.dashboard.add_panel(
        DashboardPanelCounter(
            title="Emails Traités (Prod)",
            filter=ReportFilter(metadata_values={}, tag_values=[]),
            value=PanelValue(metric_id="DatasetSummaryMetric", field_path="current.number_of_rows", legend="Emails"),
            agg=CounterAgg.LAST,
            size=WidgetSize.HALF
        )
    )
    project.save()

    # Rapport
    mapping = ColumnMapping()
    common_cols = set(ref_data.columns) & set(prod_data.columns)
    svd_cols = [c for c in common_cols if c.startswith('svd_')]
    mapping.numerical_features = svd_cols
    
    if 'target' in common_cols:
        mapping.target = 'target'
    mapping.prediction = None

    metrics_list = [
        DatasetSummaryMetric(),
        DataDriftPreset(), 
        TargetDriftPreset()
    ]

    try:
        report = Report(metrics=metrics_list)
        report.run(reference_data=ref_data, current_data=prod_data, column_mapping=mapping)
        ws.add_report(project.id, report)
        print("Rapport complet généré !")
    except Exception as e:
        import traceback
        print(f"Erreur Evidently: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    create_report()