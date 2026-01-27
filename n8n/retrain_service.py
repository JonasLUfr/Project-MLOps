from fastapi import FastAPI, HTTPException
import subprocess
import os

app = FastAPI()

NOTEBOOK_PATH = "/app/scripts/DataRetrainVectorized.ipynb"

@app.get("/")
def read_root():
    return {"status": "Retrain Service Active"}

@app.post("/retrain")
def trigger_retrain():
    """Lance le réentraînement du modèle via le notebook"""
    try:
        
        
        # Vérifier que le notebook existe
        if not os.path.exists(NOTEBOOK_PATH):
            raise HTTPException(status_code=500, detail=f"Notebook not found: {NOTEBOOK_PATH}")
        
        result = subprocess.run(
            [
                "jupyter", "nbconvert",
                "--to", "notebook",
                "--execute", NOTEBOOK_PATH,
                "--output", "DataRetrainVectorized_executed.ipynb"
            ],
            cwd="/app/scripts",
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )
        
        print(f" Return code: {result.returncode}")
        print(f" Stdout: {result.stdout[:500]}")
        print(f" Stderr: {result.stderr[:500]}")
        
        if result.returncode == 0:
            return {
                "status": "success",
                "message": "Model retrained successfully",
                "stdout": result.stdout
            }
        else:
            print(f" RETRAIN FAILED - stderr: {result.stderr}")
            print(f" RETRAIN FAILED - stdout: {result.stdout}")
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "failed",
                    "stderr": result.stderr,
                    "stdout": result.stdout
                }
            )
    except subprocess.TimeoutExpired:
        print(" TIMEOUT during retrain")
        raise HTTPException(status_code=500, detail="Retraining timeout")
    except Exception as e:
        print(f" EXCEPTION during retrain: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
