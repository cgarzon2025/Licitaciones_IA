from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import uuid
from backend import evaluar_licitacion

app = FastAPI()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Página principal (formulario)
@app.get("/", response_class=HTMLResponse)
def form():
    return """
    <html>
        <head><title>Evaluador INSITEL</title></head>
        <body>
            <h2>Evaluador de Licitaciones - INSITEL</h2>
            <form action="/evaluar" enctype="multipart/form-data" method="post">
                <input name="file" type="file" accept="application/pdf" required>
                <input type="submit" value="Evaluar">
            </form>
        </body>
    </html>
    """

# Evaluador de archivo
@app.post("/evaluar", response_class=HTMLResponse)
async def evaluar(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4()) + ".pdf"
    filepath = os.path.join(UPLOAD_FOLDER, file_id)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    resultado = evaluar_licitacion(filepath)

    if not resultado or not isinstance(resultado, dict):
        return HTMLResponse(content="<h3>Error al procesar el archivo</h3>", status_code=500)

    html = f"""
    <html>
        <head>
            <title>Resultado Evaluación</title>
            <style>
                table {{
                    border-collapse: collapse;
                    width: 80%;
                    margin: 20px auto;
                }}
                th, td {{
                    border: 1px solid #444;
                    padding: 8px 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
            </style>
        </head>
        <body>
            <h2 style="text-align:center;">Resultado de Evaluación - INSITEL</h2>
            <table>
                <tr><th colspan="2">Objeto</th></tr>
                <tr>
                    <td>¿Las actividades de INSITEL son compatibles con el objeto de la licitación?</td>
                    <td>{resultado.get("objeto", "N/A")}</td>
                </tr>

                <tr><th colspan="2">Cumplimiento con los códigos UNSPSC</th></tr>
                <tr>
                    <td>¿INSITEL cumple con los códigos solicitados?</td>
                    <td>{resultado.get("unspsc_cumple", "N/A")}</td>
                </tr>
                <tr>
                    <td>¿Cuáles incumple?</td>
                    <td>{resultado.get("unspsc_incumplidos", "Ninguno")}</td>
                </tr>

                <tr><th colspan="2">Índices Financieros y Organizacionales</th></tr>
    """

    for nombre, estado in resultado.get("indicadores", {}).items():
        html += f"<tr><td>{nombre}</td><td>{estado}</td></tr>"

    html += f"""
                <tr><th colspan="2">Conclusión</th></tr>
                <tr><td colspan="2">{resultado.get("conclusion", "N/A")}</td></tr>
            </table>
        </body>
    </html>
    """

    return HTMLResponse(content=html, media_type="text/html")