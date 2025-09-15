# Backend experiencia - versión con análisis directo de PDF vía OpenAI
import os
import re
import json
import numpy as np
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity
import mysql.connector
from mysql.connector import Error
from openai import OpenAI

# CLIENTE OpenAI - usa variable de entorno
API_KEY = os.getenv("OPENAI_API_KEY", None)
if not API_KEY:
    raise RuntimeError("Define OPENAI_API_KEY en variables de entorno.")
client = OpenAI(api_key="")

class ConexionMySQL:
    def __init__(self):
        self.conexion = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="admin",
            database="db_insitel"
        )
        self.cursor = self.conexion.cursor()

    def consultar(self, query):
        self.cursor.execute(query)
        resultados = self.cursor.fetchall()
        if not resultados:
            return []
        elif len(resultados[0]) == 1:
            return [fila[0] for fila in resultados]
        return [tuple(fila) for fila in resultados]

    def cerrar(self):
        try:
            self.cursor.close()
            self.conexion.close()
        except Exception:
            pass

def normalize_codes(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        out = set()
        for v in value:
            out.update(normalize_codes(v))
        return out
    if isinstance(value, (int, float)):
        return {str(int(value))}
    s = str(value).strip()
    if (s.startswith('[') or s.startswith('{')):
        try:
            parsed = json.loads(s)
            return normalize_codes(parsed)
        except Exception:
            pass
    s = s.strip("[](){}")
    parts = re.split(r'[\s,;|/]+', s)
    codes = set()
    for p in parts:
        token = p.strip().strip("'\"")
        if not token:
            continue
        digits = re.sub(r'\D', '', token)
        if digits:
            codes.add(digits)
    return codes

def code_matches(required_code, contract_codes, prefix_len=None):
    if required_code in contract_codes:
        return True
    if prefix_len:
        req_pref = required_code[:prefix_len]
        for c in contract_codes:
            if c.startswith(req_pref) or req_pref.startswith(c[:prefix_len]):
                return True
    return False

def evaluar_licitacion():
    db = None
    try:
        # 1) Cargar datos desde DB
        db = ConexionMySQL()
        lista_experiencia = db.consultar("SELECT consecutivo, objeto, smmlv FROM experiencia;")
        lista_codigos_contrato = db.consultar("SELECT consecutivo, codigos_unspsc FROM contratos;")
        diccionario_contratos = {}
        for consecutivo, codigos in lista_codigos_contrato:
            diccionario_contratos.setdefault(consecutivo, []).append(codigos)

        # 2) Subir PDF a OpenAI
        pdf_path = "PruebaLicitacion2.pdf"
        archivo = client.files.create(file=open(pdf_path, "rb"), purpose="user_data")

        # 2.1 Extraer el objeto
        resp_objeto = client.responses.create(
            model='gpt-4o',
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": archivo.id},
                        {"type": "input_text", "text": (
                            "Extrae el objeto del documento, busca únicamente el objeto como tal. "
                            "No incluyas explicaciones ni texto adicional, solo el objeto."
                        )}
                    ]
                }
            ]
        )
        objeto = resp_objeto.output_text.strip()
        if not objeto:
            raise RuntimeError("No se pudo extraer el objeto del documento.")

        # 3) Batch embeddings de experiencias
        textos_experiencias = [obj for (_, obj, _) in lista_experiencia]
        if not textos_experiencias:
            print("No hay experiencias en la DB.")
            return False

        emb_res = client.embeddings.create(
            model="text-embedding-3-small",
            input=textos_experiencias
        )
        vectores_exp = [np.array(item.embedding) for item in emb_res.data]

        # Embedding del objeto
        emb_objeto = client.embeddings.create(model="text-embedding-3-small", input=objeto)
        vec_obj = np.array(emb_objeto.data[0].embedding).reshape(1, -1)

        # 4) Similaridad
        simil = cosine_similarity(vec_obj, vectores_exp)[0]
        top_k = 3
        top_indices = np.argsort(simil)[-top_k:][::-1]

        ponderaciones = [0.7, 0.2, 0.1][:len(top_indices)]
        sim_ponderada = sum(simil[idx] * ponderaciones[i] for i, idx in enumerate(top_indices))
        sim_prom = sim_ponderada / sum(ponderaciones)
        cumple_obj = "SI" if sim_prom >= 0.55 else "NO"

        # 5) Extraer experiencia en JSON
        prompt_system = (
            "Eres un asistente experto en análisis de pliegos de condiciones de licitaciones. "
            "Tu tarea es analizar el documento proporcionado y extraer la información sobre los requisitos de experiencia solicitados. "
            "Debes devolver únicamente un objeto JSON válido con las claves: experiencia_general y experiencia_especifica. "
            "Si un campo no aparece, usar valores por defecto: numero_contratos=1, condicion_experiencia='minimo', porcentaje=1.0, "
            "valor_smlmv=0, antiguedad=0. Convertir porcentajes a decimales. No incluir texto fuera del JSON."
        )

        resp_exper = client.responses.create(
            model='gpt-4o',
            input=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": [
                    {"type": "input_file", "file_id": archivo.id},
                    {"type": "input_text", "text": "Analiza el documento y devuelve el JSON solicitado con la experiencia general y específica."}
                ]}
            ]
        )
        experiencia_text = resp_exper.output_text

        print("DEBUG - Respuesta cruda del modelo:\n", experiencia_text)

        # Limpiar JSON
        texto_limpio = re.sub(r"```(?:json)?\n?", "", experiencia_text, flags=re.IGNORECASE)
        texto_limpio = re.sub(r"\n?```", "", texto_limpio)
        match = re.search(r'({.*})', texto_limpio, re.DOTALL)
        if match:
            texto_limpio = match.group(1)
        if not texto_limpio.strip():
            raise RuntimeError("El modelo no devolvió un JSON válido. Revisa la respuesta cruda ↑")

        data = json.loads(texto_limpio.strip())
        exp_gen = data.get("experiencia_general", {})

        presupuesto_general = exp_gen.get("presupuesto_oficial", 0.0)
        iva_general = exp_gen.get("IVA", False)
        condicion_general = exp_gen.get("condicion_experiencia", "minimo")
        num_contratos_general = int(exp_gen.get("numero_contratos", 1))
        porcentaje_general = float(exp_gen.get("porcentaje", 1.0))
        valor_smlmv_general = float(exp_gen.get("valor_smlmv", 0.0))
        codigos_general = exp_gen.get("codigos", [])
        antiguedad_general = int(exp_gen.get("antiguedad", 0))

        if valor_smlmv_general == 0 and presupuesto_general:
            valor_smlmv_general = float(presupuesto_general) / 1423500  # SMMLV base

        # 6) Matching de códigos
        codigos_requeridos = normalize_codes(codigos_general)
        contratos_validos = []
        per_contract_threshold = 1.0
        prefix_len = 6

        for contrato_id, raw_codigos in diccionario_contratos.items():
            codigos_contrato = normalize_codes(raw_codigos)
            if not codigos_requeridos:
                contratos_validos.append(contrato_id)
                continue
            matches = sum(1 for rc in codigos_requeridos if code_matches(rc, codigos_contrato, prefix_len=prefix_len))
            ratio = matches / max(1, len(codigos_requeridos))
            if ratio >= per_contract_threshold:
                contratos_validos.append(contrato_id)

        contratos_similares = [lista_experiencia[idx][0] for idx in top_indices]
        contratos_candidatos_finales = list(set(contratos_validos) & set(contratos_similares))
        cumple_total = "SI" if len(contratos_candidatos_finales) >= num_contratos_general else "NO"

        def convertir_a_float(valor):
            try:
                return float(valor)
            except Exception:
                return 0.0

        contratos_ordenados_similitud = [c for c in contratos_similares if c in contratos_candidatos_finales]
        contratos_usados = [
            (consec, convertir_a_float(smmlv))
            for consecutivo, _, smmlv in lista_experiencia
            for consec in [consecutivo]
            if consecutivo in contratos_ordenados_similitud[:num_contratos_general]
        ]
        total_smmlv_requerido = sum(sm for _, sm in contratos_usados)
        cumple_smlmv = total_smmlv_requerido >= valor_smlmv_general

        conclusion = "Vale la pena Revisar la Licitación" if (cumple_obj == "SI" and cumple_smlmv) else "Descartar Licitación"

        # Impresión de resultados
        print('***** RESULTADO FINAL *****\n')
        print('1. OBJETO:')
        print(f'Objeto extraído: {objeto[:200]}{"..." if len(objeto)>200 else ""}')
        print(f'Cumple con el objeto solicitado: {cumple_obj}\n')

        print('4. EXPERIENCIA:')
        print(f'Valor en SMMLV solicitado: {valor_smlmv_general}')
        print(f'Se requieren mínimo {num_contratos_general} contrato(s) con experiencia.')
        print('Contratos usados (por similitud y códigos):')
        for consecutivo, smmlv in contratos_usados:
            print(f' - Contrato {consecutivo}: {smmlv} SMMLV')
        print(f'Total SMMLV aportado: {total_smmlv_requerido}')
        print(f'¿Cumple con experiencia solicitada?: {"SI" if cumple_smlmv else "NO"}\n')

        print('5. CONCLUSIÓN:')
        print(f'Conclusión general: {conclusion}')

        return True

    except Exception as e:
        print("Error en evaluar_licitacion():", str(e))
        return False

    finally:
        if db:
            db.cerrar()

if __name__ == "__main__":
    evaluar_licitacion()
