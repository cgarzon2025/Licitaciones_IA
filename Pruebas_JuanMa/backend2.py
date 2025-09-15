#   ***** BACKEND EXPERIENCIA PARA PROYECTO LICITACIONES CON IA *****

# LIBRERIAS NECESARIAS
from openai import OpenAI
import mysql.connector
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import re, json, os
from pydantic import BaseModel, Field

# LLAMADO A LLAVE DE OPEN AI
client = OpenAI(api_key="")

# CLASE PARA CONEXION A DB MYSQL
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
        self.cursor.close()
        self.conexion.close()

# FUNCION PRINCIPAL
def evaluar_licitacion():
    # ALMACENAR LISTAS DE DATOS NECESARIOS
    db = ConexionMySQL()
    lista_experiencia = db.consultar("SELECT consecutivo, objeto, smmlv FROM experiencia;")

    # LISTA DE CODIGOS DE CADA CONTRATO
    lista_codigos_contrato = db.consultar("SELECT consecutivo, codigos_unspsc FROM contratos;")
    diccionario_contratos = {}
    for consecutivo, codigos in lista_codigos_contrato:
        if consecutivo not in diccionario_contratos:
            diccionario_contratos[consecutivo] = []
        diccionario_contratos[consecutivo].append(codigos)

    # SUBIR ARCHIVO
    archivo = client.files.create(file=open('PruebaLicitacion1.pdf', "rb"), purpose="user_data")

    # ****** OBJETO ******
    # EXTRAER OBJETO
    objeto = client.responses.create(
        model='gpt-4o',
        input=[
            {
                'role': 'user',
                'content': [
                    {'type': 'input_file', 'file_id': archivo.id},
                    {'type': 'input_text', 'text': (
                        'Extrae el objeto del documento, busca únicamente el objeto como tal '
                        "No incluyas explicaciones ni texto adicional, solo el objeto."
                    )}
                ]
            }
        ]
    ).output_text.strip()

    # CONVERSION DE EXPERIENCIAS A EMBEDDING
    array_exp = []
    for consecutivo, objeto, smmlv in lista_experiencia:
        emb = client.embeddings.create(
            model="text-embedding-3-small",
            input=objeto  # solo el texto del objeto
        )
        array_exp.append({
            "consecutivo": consecutivo,
            "embedding": emb.data[0].embedding,
            "smmlv": smmlv
        })
    vectores_exp = [np.array(item["embedding"]) for item in array_exp]

    # CONVERSION DE OBJETO A EMBEDDING
    emb_objeto = client.embeddings.create(model="text-embedding-3-small", input=objeto)

    # COMPARACION CON FUNCION COSINE DE EMBEDDINGS
    simil = cosine_similarity([np.array(emb_objeto.data[0].embedding)], vectores_exp)[0]
    top_indices = simil.argsort()[-3:][::-1]

    # LISTA DE TEXTOS MAS SIMILARES Y PROMEDIO DE SIMILITUD
    text_similares = []
    sim_ponderada = 0
    ponderaciones = [0.8, 0.15, 0.05]

    for i, idx in enumerate(top_indices):
        text_similares.append(lista_experiencia[idx][1])
        sim_ponderada += simil[idx] * ponderaciones[i]
    sim_prom = sim_ponderada / sum(ponderaciones)

    # OBTENER CONTRATOS MÁS SIMILARES POR CONSECUTIVO
    contratos_similares = [lista_experiencia[idx][0] for idx in top_indices]
    #print(type(objeto))
    #print(objeto)
    #print(type(contratos_similares))
    #print(contratos_similares)

    cumple_obj = "SI" if sim_prom >= 0.55 else "NO"

# EXTRAER DATOS EXPERIENCIA GENERAL
    experiencia = client.responses.create(
        model='gpt-4o',
        input=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente experto en análisis de pliegos de condiciones de licitaciones. "
                    "Tu tarea es analizar el documento proporcionado y extraer la información sobre los requisitos de experiencia solicitados. "
                    "Debes devolver únicamente un objeto JSON válido en el siguiente formato:\n\n"
                    "{\n"
                    "  \"experiencia_general\": {\n"
                    "    \"presupuesto_oficial\": float,  // Valor numérico del presupuesto oficial (puede aparecer como 'valor estimado', 'presupuesto oficial' u otros términos similares)\n"
                    "    \"IVA\": boolean,  // True si el presupuesto incluye IVA, False en caso contrario\n"
                    "    \"numero_contratos\": int,  // Número de contratos ejecutados requeridos para verificar la experiencia del proponente; si no se menciona, usar 1\n"
                    "    \"condicion_experiencia\": string,  // condicion que debe cumplir el número de contratos: \"minimo\", \"maximo\", \"igual\"\n"
                    "    \"porcentaje\": float,  // Porcentaje en valor decimal (80% → 0.8); si no se menciona, usar 1.0\n"
                    "    \"valor_smlmv\": float,  // Valor en salarios mínimos; si no se menciona, usar 0\n"
                    "    \"codigos\": [string],  // Lista de códigos UNSPSC solicitados\n"
                    "    \"antiguedad\": int  // Años mínimos de antigüedad de los contratos; si no se menciona, usar 0\n"
                    "  },\n"
                    "  \"experiencia_especifica\": {\n"
                    "    // Si sigue la misma estructura que experiencia_general, devolver un objeto con la misma estructura.\n"
                    "    // Si es diferente, devolver un string con la descripción encontrada.\n"
                    "    // Si no existe experiencia específica, devolver false.\n"
                    "  }\n"
                    "}\n\n"
                    "Reglas:\n"
                    "- Si un campo no aparece, usar el valor por defecto indicado.\n"
                    "- Si el documento no especifica si la experiencia es general o específica se toma como general .\n"
                    "- Si el documento sí menciona un número de contratos para validar la experiencia pero no menciona si es máximo o mínimi debe asignarse igual a la condición.\n"
                    "- Si el documento NO menciona el número de cotratos debe asignarse 1 a numero de contrato y 'minimo' la condición.\n"
                    "- Convertir todos los porcentajes a valores decimales.\n"
                    "- El JSON devuelto debe ser válido y sin comentarios.\n"
                    "- No incluir texto adicional fuera del JSON."
                )
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": archivo.id},
                    {"type": "input_text",
                     "text": "Analiza el documento y devuelve el JSON solicitado con la experiencia general y específica."}
                ]
            }
        ]
    ).output_text

    # ELIMINAR ETIQUETAS MARKDOWN TIPO JSON Y TEXTO ANTES O DESPUES DEL JSON SI EXISTIERA
    texto_limpio = re.sub(r"```(?:json)?\n?", "", experiencia, flags=re.IGNORECASE)
    texto_limpio = re.sub(r"\n?```", "", texto_limpio)
    match = re.search(r'({.*})', texto_limpio, re.DOTALL)
    if match:
        texto_limpio = match.group(1)

    # SE PARSEA LOS DATOS DE JSON
    data = json.loads(texto_limpio.strip())
    exp_gen = data["experiencia_general"]

    # SE EXTRAE LAS VARIABLES DE LA EXPERIENCIA GENERAL
    presupuesto_general = exp_gen["presupuesto_oficial"]
    #print(presupuesto_general)
    iva_general = exp_gen["IVA"]
    #print(iva_general)
    condicion_general = exp_gen["condicion_experiencia"]
    #print(condicion_general)
    num_contratos_general = exp_gen["numero_contratos"]
    #print(num_contratos_general)
    porcentaje_general = exp_gen["porcentaje"]
    #print(porcentaje_general)
    valor_smlmv_general = exp_gen["valor_smlmv"]
    #print(valor_smlmv_general)
    codigos_general = exp_gen["codigos"]
    #print(codigos_general)
    antiguedad_general = exp_gen["antiguedad"]
    #print(antiguedad_general)

    #VALIDAR SI EL VALOR DE PRESUPUESTO VIENE EN SALARIOS MINIMOS
    if valor_smlmv_general != 0:
        valor_smlmv_general = valor_smlmv_general
    else:
        valor_smlmv_general = float(presupuesto_general)/1423500

    def normalize_codes(value):
        """Normaliza distintos formatos a un set de códigos (solo dígitos).
           Maneja listas, strings tipo 'a,b', JSON string, None, etc.
        """
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
        # intentar parse JSON
        if (s.startswith('[') or s.startswith('{')):
            try:
                parsed = json.loads(s)
                return normalize_codes(parsed)
            except Exception:
                pass
        # quitar corchetes exteriores y comillas
        s = s.strip("[](){}")
        parts = re.split(r'[\s,;|/]+', s)
        codes = set()
        for p in parts:
            token = p.strip().strip("'\"")
            if not token:
                continue
            # extraer solo dígitos (UNSPSC suelen ser dígitos)
            digits = re.sub(r'\D', '', token)
            if digits:
                codes.add(digits)
        return codes
    def code_matches(required_code, contract_codes, prefix_len=None):
        """True si hay match exacto o por prefijo (si prefix_len dado)."""
        if required_code in contract_codes:
            return True
        if prefix_len:
            req_pref = required_code[:prefix_len]
            for c in contract_codes:
                if c.startswith(req_pref) or req_pref.startswith(c[:prefix_len]):
                    return True
        return False
    def get_codes_for_id(cid, diccionario_contratos):
        """Acceso tolerante: busca key tal cual, como str o por comparación str()."""
        if cid in diccionario_contratos:
            return diccionario_contratos[cid]
        scid = str(cid)
        if scid in diccionario_contratos:
            return diccionario_contratos[scid]
        for k, v in diccionario_contratos.items():
            if str(k) == scid:
                return v
        return []

    # --- Reemplaza tu bloque de validación por este ---
    codigos_requeridos = normalize_codes(codigos_general)
    #print("DEBUG - codigos_requeridos:", codigos_requeridos)
    contratos_validos = []
    # parámetros (ajustables)
    per_contract_threshold = 1  # umbral % por contrato (0..1)
    prefix_len = 6  # comparar por los primeros 6 dígitos si no hay match exacto
    allow_partial = True

    for contrato_id, raw_codigos in diccionario_contratos.items():
        codigos_contrato = normalize_codes(raw_codigos)
        #print(f"DEBUG - contrato {contrato_id} codigos_contrato (normalized): {sorted(list(codigos_contrato))[:10]} ... (total {len(codigos_contrato)})")

        if not codigos_requeridos:
            contratos_validos.append(contrato_id)
            continue

        matches = sum(1 for rc in codigos_requeridos if code_matches(rc, codigos_contrato, prefix_len=prefix_len))
        ratio = matches / len(codigos_requeridos)
        #print(f"DEBUG - contrato {contrato_id} matches {matches}/{len(codigos_requeridos)} ratio {ratio:.2f}")

        if ratio >= per_contract_threshold:
            contratos_validos.append(contrato_id)

    #print("DEBUG - contratos_validos:", contratos_validos)
    #print(f'Contratos que cumplen con los códigos (según criterio): {contratos_validos}')

    # INTERSECCION ENTRE CONTRATOS VALIDADOS POR CODIGO Y POR SIMILITUD
    contratos_candidatos_finales = list(set(contratos_validos) & set(contratos_similares))
    #print(f"Contratos que cumplen con Códigos y Similitud de Objeto: {contratos_candidatos_finales}")

    # VALIDAR SI ALCANZA NUMERO DE CONTRATOS REQUERIDOS
    cumple_total = "SI" if len(contratos_candidatos_finales) >= num_contratos_general else "NO"
    #print(f"¿Cumple número mínimo de contratos requeridos ({num_contratos_general})?: {cumple_total}")

    # Sumar los valores SMMLV de los contratos válidos
    def convertir_a_float(valor):
        try:
            return float(valor)
        except ValueError:
            return 0

    # Paso 1: Filtrar los contratos que están tanto en contratos_similares como en contratos_candidatos_finales
    contratos_ordenados_similitud = [
        contrato for contrato in contratos_similares if contrato in contratos_candidatos_finales
    ]

    # Paso 2: obtener los contratos usados con su smmlv
    contratos_usados = [
        (consecutivo, convertir_a_float(smmlv))
        for consecutivo, _, smmlv in lista_experiencia
        if consecutivo in contratos_ordenados_similitud[:num_contratos_general]
    ]

    # Ya puedes usar directamente:
    total_smmlv_requerido = sum(smmlv for _, smmlv in contratos_usados)

    # Aplicar el porcentaje si es necesario
    #valor_requerido = valor_smlmv_general * porcentaje_general

    # Validar según la condición del pliego
    if total_smmlv_requerido >= valor_smlmv_general:
        cumple_smlmv = True
    else:
        cumple_smlmv = False

    # CONCLUSION LOGICA BASICA FINAL
    conclusion = (
        "Vale la pena Revisar la Licitación" if cumple_obj == "SI" and cumple_smlmv == True else "Descartar Licitación")

    print('***** RESULTADO FINAL *****\n')

    # 1. OBJETO
    print('1. OBJETO:')
    print(f'Cumple con el objeto solicitado: {cumple_obj}\n')

    # 4. EXPERIENCIA Y VALOR SMMLV
    print('4. EXPERIENCIA:')
    print(f'Valor en SMMLV solicitado: {valor_smlmv_general}')
    print(f'Se requieren mínimo {num_contratos_general} contrato(s) con experiencia.')
    print(f'Contratos usados (por similitud y códigos):')
    for consecutivo, smmlv in contratos_usados:
        print(f' - Contrato {consecutivo}: {smmlv} SMMLV')
    print(f'Total SMMLV aportado: {total_smmlv_requerido}')
    print(f'¿Cumple con experiencia solicitada?: {"SI" if cumple_smlmv else "NO"}\n')

    # 5. CONCLUSIÓN FINAL
    print('5. CONCLUSIÓN:')
    print(f'Conclusión general: {conclusion}')
    return True

if __name__ == "__main__":
    evaluar_licitacion()



