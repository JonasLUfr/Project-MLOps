import pandas as pd
import os
import time
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, ClassificationPreset, TargetDriftPreset
from evidently.ui.workspace import Workspace
from evidently.pipeline.column_mapping import ColumnMapping
from evidently.ui.dashboards import DashboardPanelCounter, PanelValue, ReportFilter

# path (accessibles via le volume Docker)
REF_DATA_PATH = "/data/ref_data.csv"
PROD_DATA_PATH = "/data/prod_data.csv"
WORKSPACE_PATH = "workspace" # dossier local dans le conteneur pour stocker la BDD Evidently

def create_report():
    if not os.path.exists(REF_DATA_PATH):
        print("❌ Erreur : ref_data.csv introuvable.")
        return
    # chargement des données
    ref_data = pd.read_csv(REF_DATA_PATH)
    
    if not os.path.exists(PROD_DATA_PATH):
        print("⚠️ prod_data.csv n'existe pas encore. Rapport impossible.")
        return
        
    prod_data = pd.read_csv(PROD_DATA_PATH)
    
    if len(prod_data) < 2:
        print("⚠️ Pas assez de données de production pour générer un rapport.")
        return

    print(f"📊 Génération du rapport avec {len(ref_data)} lignes de ref et {len(prod_data)} lignes de prod...")

    # config du Workspace Evidently
    ws = Workspace.create(WORKSPACE_PATH)
    
    # on crée le projet s'il n'existe pas
    project_name = "Churn Monitoring"
    project = None
    
    # recherche du projet existant
    search = ws.search_project(project_name)
    if search:
        project = search[0]
    else:
        project = ws.create_project(project_name)
        project.description = "Monitoring du modèle de Churn"

        project.dashboard.add_panel(
            DashboardPanelCounter(
                title="Nombre de lignes traitées",
                filter=ReportFilter(metadata_values={}, tag_values=[]),
                value=PanelValue(
                    metric_id="DatasetMissingValuesMetric", 
                    field_path="current.number_of_rows", 
                    legend="Lignes (Prod)"
                )
            )
        )

        project.save()


    # on précise à Evidently quelles colonnes utiliser
    # si 'prediction' n'est pas dans ref_data, on ne peut pas calculer le drift dessus
    # donc on va lister les métriques une par une pour éviter celles qui plantent
    
    # on verif si 'prediction' est bien dans les deux fichiers
    include_prediction_metrics = 'prediction' in ref_data.columns and 'prediction' in prod_data.columns
    
    metrics_list = [
        #DataDriftPreset(),       # verif si les donnees drift (PCA) -> pas update au format text
        TargetDriftPreset()      # verif si la cible change
    ]

    # config du mapping
    data_mapping = ColumnMapping()
    
    if include_prediction_metrics:
        # si on a la prédiction partout, on ajoute les métriques de classification
        metrics_list.append(ClassificationPreset()) # verif la performance (F1, Accuracy..., si 'target' est présent
        data_mapping.prediction = 'prediction'
    else:
        print("⚠️ Colonne 'prediction' absente de ref_data. Les métriques de classification seront ignorées.")
        # dans ce cas, on force Evidently à ignorer la colonne prediction
        data_mapping.prediction = None

    report = Report(metrics=metrics_list)
    report.run(reference_data=ref_data, current_data=prod_data, column_mapping=data_mapping)

    # save dans le Workspace (pour que l'UI le voie)
    ws.add_report(project.id, report)
    print("✅ Rapport généré et envoyé au Dashboard !")

if __name__ == "__main__":
    # petit délai pour être sûr que le volume soit monté
    time.sleep(2)
    create_report()