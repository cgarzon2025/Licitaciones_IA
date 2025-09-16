from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import os
import shutil
import uuid

from backend1 import evaluar_licitacion as evaluar_financiero
from backend2 import evaluar_licitacion as evaluar_experiencia

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

    # Llamar a ambos backends
    resultado_financiero = evaluar_financiero(filepath)
    resultado_experiencia = evaluar_experiencia(filepath)

    if not resultado_financiero or not isinstance(resultado_financiero, dict):
        return HTMLResponse(content="<h3>Error en análisis financiero/UNSPSC</h3>", status_code=500)
    if not resultado_experiencia or not isinstance(resultado_experiencia, dict):
        return HTMLResponse(content="<h3>Error en análisis de experiencia</h3>", status_code=500)

    # HTML combinado con f-strings (evita KeyError en CSS)
    html = f"""
    <html>
        <head>
            <title>Resultado Evaluación Integrada</title>
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
                .section-title {{
                    background: #ddd;
                    text-align: center;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <h2 style="text-align:center;">Resultado de Evaluación - INSITEL</h2>
            <table>
                <tr><th colspan="2" class="section-title">Evaluación Financiera / UNSPSC</th></tr>
                <tr><td>Objeto</td><td>{resultado_financiero.get("objeto", "N/A")}</td></tr>
                <tr><td>¿Cumple UNSPSC?</td><td>{resultado_financiero.get("unspsc_cumple", "N/A")}</td></tr>
                <tr><td>Incumplidos</td><td>{resultado_financiero.get("unspsc_incumplidos", "Ninguno")}</td></tr>

                <tr><th colspan="2" class="section-title">Evaluación de Experiencia</th></tr>
                <tr><td>Objeto</td><td>{resultado_experiencia.get("objeto", "N/A")}</td></tr>
                <tr><td>¿Compatibilidad con objeto?</td><td>{resultado_experiencia.get("cumple_objeto", "N/A")}</td></tr>
                <tr><td>SMMLV solicitado</td><td>{resultado_experiencia.get("valor_smlmv_solicitado", "N/A")}</td></tr>
                <tr><td>Mínimo de contratos</td><td>{resultado_experiencia.get("num_contratos_requeridos", "N/A")}</td></tr>
                <tr><td>Total SMMLV aportado</td><td>{resultado_experiencia.get("total_smmlv_aportado", "N/A")}</td></tr>
                <tr><td>¿Cumple experiencia?</td><td>{resultado_experiencia.get("cumple_experiencia", "N/A")}</td></tr>
    """

    # Contratos usados (backend2)
    contratos = resultado_experiencia.get("contratos_usados", [])
    if contratos:
        html += "<tr><td colspan='2'><b>Contratos usados:</b><ul>"
        for consecutivo, smmlv in contratos:
            html += f"<li>Contrato {consecutivo}: {smmlv} SMMLV</li>"
        html += "</ul></td></tr>"

    # Conclusión final
    conclusion_fin = resultado_financiero.get("conclusion", "N/A")
    conclusion_exp = resultado_experiencia.get("conclusion", "N/A")
    conclusion_global = "Vale la pena Revisar la Licitación" if (
        "SI" in [resultado_financiero.get("unspsc_cumple"), resultado_experiencia.get("cumple_experiencia")]
    ) else "Descartar Licitación"

    html += f"""
                <tr><th colspan="2" class="section-title">Conclusiones</th></tr>
                <tr><td>Financiera/UNSPSC</td><td>{conclusion_fin}</td></tr>
                <tr><td>Experiencia</td><td>{conclusion_exp}</td></tr>
                <tr><td><b>Conclusión Global</b></td><td><b>{conclusion_global}</b></td></tr>
            </table>
        </body>
    </html>
    """

    return HTMLResponse(content=html, media_type="text/html")