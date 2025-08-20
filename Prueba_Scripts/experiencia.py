from openai import OpenAI
import mysql.connector
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import re, json, os
from pydantic import BaseModel, Field

# LLAMADO A LLAVE DE OPEN AI
client = OpenAI(api_key="")
# SUBIR ARCHIVO
archivo = client.files.create(file=open('PruebaLicitacion1.pdf', "rb"), purpose="user_data")
# CONEXION A BASE DE DATOS
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
db = ConexionMySQL()
# LISTA DE EXPERIENCIA
lista_experiencia = db.consultar("SELECT consecutivo, objeto, smmlv FROM experiencia;")
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
# OBTENER CONTRATOS MÁS SIMILARES POR CONSECUTIVO
contratos_similares = [lista_experiencia[idx][0] for idx in top_indices]
# LISTA CODIGOS CONTRATOS
lista_codigos_contrato = db.consultar("SELECT consecutivo, codigos_unspsc FROM contratos;")
diccionario_contratos = {}
for consecutivo, codigos in lista_codigos_contrato:
    if consecutivo not in diccionario_contratos:
        diccionario_contratos[consecutivo] = []
    diccionario_contratos[consecutivo].append(codigos)
# EXTRAER EXPERIENCIA
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
iva_general = exp_gen["IVA"]
condicion_general = exp_gen["condicion_experiencia"]
num_contratos_general = exp_gen["numero_contratos"]
porcentaje_general = exp_gen["porcentaje"]
valor_smlmv_general = exp_gen["valor_smlmv"]
codigos_general = exp_gen["codigos"]
antiguedad_general = exp_gen["antiguedad"]
#VALIDAR SI EL VALOR DE PRESUPUESTO VIENE EN SALARIOS MINIMOS
if valor_smlmv_general != 0:
    valor_smlmv_general = valor_smlmv_general
else:
    valor_smlmv_general = float(presupuesto_general)/1423500
#VALIDAR CODIGOS REQUERIDOS EN CONTRATOS ACTUALES
codigos_requeridos = set(codigos_general)  # De tu JSON extraído
contratos_validos = []
for contrato_id, codigos in diccionario_contratos.items():
    codigos_contrato = set(codigos)
    if codigos_requeridos.issubset(codigos_contrato):
        contratos_validos.append(contrato_id)
print(f'Contratos que cumplen con el 100% de los códigos requeridos: {contratos_validos}')
# INTERSECCION ENTRE CONTRATOS VALIDADOS POR CODIGO Y POR SIMILITUD
contratos_candidatos_finales = list(set(contratos_validos) & set(contratos_similares))
print(f"Contratos que cumplen con Códigos y Similitud de Objeto: {contratos_candidatos_finales}")
# VALIDAR SI ALCANZA NUMERO DE CONTRATOS REQUERIDOS
cumple_total = "SI" if len(contratos_candidatos_finales) >= num_contratos_general else "NO"
print(f"¿Cumple número mínimo de contratos requeridos ({num_contratos_general})?: {cumple_total}")
# Sumar los valores SMMLV de los contratos válidos
def convertir_a_float(valor):
    try:
        return float(valor)
    except ValueError:
        return 0
# Filtrar los contratos que están tanto en contratos_similares como en contratos_candidatos_finales
contratos_ordenados_similitud = [
    contrato for contrato in contratos_similares if contrato in contratos_candidatos_finales
]
# Obtener los contratos usados con su smmlv
contratos_usados = [
    (consecutivo, convertir_a_float(smmlv))
    for consecutivo, _, smmlv in lista_experiencia
    if consecutivo in contratos_ordenados_similitud[:num_contratos_general]
]
# SUMA
total_smmlv_requerido = sum(smmlv for _, smmlv in contratos_usados)
# Validar según la condición del pliego
if total_smmlv_requerido >= valor_smlmv_general:
    cumple_smlmv = True
else:
    cumple_smlmv = False

# 4. EXPERIENCIA Y VALOR SMMLV
print('4. EXPERIENCIA:')
print(f'Valor en SMMLV solicitado: {valor_smlmv_general}')
print(f'Se requieren mínimo {num_contratos_general} contrato(s) con experiencia.')
print(f'Contratos usados (por similitud y códigos):')
for consecutivo, smmlv in contratos_usados:
    print(f' - Contrato {consecutivo}: {smmlv} SMMLV')
print(f'Total SMMLV aportado: {total_smmlv_requerido}')
print(f'¿Cumple con experiencia solicitada?: {"SI" if cumple_smlmv else "NO"}\n')