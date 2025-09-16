from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import os
import shutil
import uuid
from backend2 import evaluar_licitacion  # asegúrate que backend1.py tenga la función modificada

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
                <input name="file" type="file" accept="application/pdf" required>
                <input type="submit" value="Evaluar">
            </form>
        </body>
    </html>
    """

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
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }}
                table {{
                    border-collapse: collapse;
                    width: 90%;
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
                    <td>Objeto extraído</td>
                    <td>{resultado.get("objeto", "N/A")}</td>
                </tr>
                <tr>
                    <td>¿Compatibilidad con objeto?</td>
                    <td>{resultado.get("cumple_objeto", "N/A")}</td>
                </tr>

                <tr><th colspan="2">Experiencia</th></tr>
                <tr>
                    <td>SMMLV solicitado</td>
                    <td>{resultado.get("valor_smlmv_solicitado", "N/A")}</td>
                </tr>
                <tr>
                    <td>Mínimo de contratos</td>
                    <td>{resultado.get("num_contratos_requeridos", "N/A")}</td>
                </tr>
                <tr>
                    <td>Total SMMLV aportado</td>
                    <td>{resultado.get("total_smmlv_aportado", "N/A")}</td>
                </tr>
                <tr>
                    <td>¿Cumple experiencia?</td>
                    <td>{resultado.get("cumple_experiencia", "N/A")}</td>
                </tr>
    """

    # Contratos usados
    contratos = resultado.get("contratos_usados", [])
    if contratos:
        html += "<tr><td colspan='2'><b>Contratos usados:</b><ul>"
        for consecutivo, smmlv in contratos:
            html += f"<li>Contrato {consecutivo}: {smmlv} SMMLV</li>"
        html += "</ul></td></tr>"

    html += f"""
                <tr><th colspan="2">Conclusión</th></tr>
                <tr><td colspan="2">{resultado.get("conclusion", "N/A")}</td></tr>
            </table>
        </body>
    </html>
    """

    return HTMLResponse(content=html, media_type="text/html")
