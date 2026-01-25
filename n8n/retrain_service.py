from fastapi import FastAPI, HTTPException
import subprocess
import os

app = FastAPI()

NOTEBOOK_PATH = "/app/scripts/DataModeling.ipynb"

@app.get("/")
def read_root():
    return {"status": "Retrain Service Active"}

@app.post("/retrain")
def trigger_retrain():
    """Lance le réentraînement du modèle via le notebook"""
    try:
        result = subprocess.run(
            [
                "jupyter", "nbconvert",
                "--to", "notebook",
                "--execute", NOTEBOOK_PATH,
                "--output", "DataModeling_executed.ipynb"
            ],
            cwd="/app/scripts",
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )
        
        if result.returncode == 0:
            return {
                "status": "success",
                "message": "Model retrained successfully",
                "stdout": result.stdout
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "failed",
                    "stderr": result.stderr,
                    "stdout": result.stdout
                }
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Retraining timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
