# main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from procesador import evaluar_licitacion
import shutil
import uuid
import os

app = FastAPI()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def form():
    return """
    <html>
        <head><title>Evaluador INSITEL</title></head>
        <body>
            <h2>Evaluador de Licitaciones - INSITEL</h2>
            <form action="/evaluar" enctype="multipart/form-data" method="post">
                <input name="file" type="file" accept="application/pdf">
                <input type="submit">
            </form>
        </body>
    </html>
    """
#cambios

@app.post("/evaluar")
async def evaluar(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4()) + ".pdf"
    filepath = os.path.join(UPLOAD_FOLDER, file_id)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    resultado = evaluar_licitacion(filepath)
    return JSONResponse(content=resultado)
