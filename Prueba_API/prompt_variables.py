# PRUEBA USANDO UN SOLO PROMPT PARA QUE EXTRAIGA TODAS LAS VARIABLES
# LIBRERIAS NECESARIAS
from openai import OpenAI
import mysql.connector
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import re, json, os
from pydantic import BaseModel, Field

# LLAMADO A LLAVE DE OPEN AI
client = OpenAI(api_key="")  # Reemplazar con tu clave real

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

# SUBIR ARCHIVO
archivo = client.files.create(file=open('PruebaLicitacion1.pdf', "rb"), purpose="user_data")

response = client.responses.create(
    model='gpt-4o',
    input=[
        {
            'role': 'system',
            'content': (
                "Eres un asistente experto en análisis de pliegos de condiciones de licitaciones. "
                "Tu tarea es extraer las variables claves para determinar si una licitación es viable revisarla o no, se debe extraer: Objeto, Codigos UNSPSC,"
                "Indicadores Financieros (indice de liquidez, indice de endeudamiento, razon de cobertura de intereses, rentabilidad de patrimonio y rentabilidad de activo),"
                "Experiencia General (valor presupuesto, valor en smlmv, iva, numero de contratos minimos, codigos unspsc experiencia)"
                "Objeto: Extrae el objeto del documento, busca únicamente el objeto como tal"
                "Codigos UNSPSC: Tu tarea es identificar y extraer todos los códigos UNSPSC presentes en el contenido que se te proporcione. "
                    "Los códigos UNSPSC pueden estar escritos de forma completa (8 dígitos seguidos), segmentada (por ejemplo: 43 22 25 01), "
                    "o distribuidos en tablas con celdas vacías, lo que implica que los valores deben heredarse de filas anteriores para formar un código completo. "
                    "Si un código tiene solo segmento, familia y clase (6 dígitos completos), complétalo siempre con dos ceros al final para formar un código de 8 dígitos. "
                    "Solo extrae códigos que tengan al menos 6 dígitos completos con valores distintos de cero. "
                    "Descarta códigos incompletos o códigos que solo tengan segmento o segmento + familia (por ejemplo: 41000000 o 43210000). "
                    "Reconstruye cada código UNSPSC como una cadena de 8 dígitos. "
                "Indicadores Financieros: Tu tarea es extraer los indicadores financieros de los documentos proporcionados ('Indice de Liquidez', 'Indice de Endeudamiento', 'Razón de Cobertura de Interes' 'Rentabilidad del Patrimonio' y 'Rentabilidad del Activo'), "
                    "asegurarte de estandarizar todos los valores (elimina símbolos como '$', '%', comas, puntos de miles o caracteres no numéricos) "
                    "y convertir porcentajes a decimales cuando corresponda. "
                    "Luego compara cada indicador solicitado con el correspondiente de la base INSITEL,"
                " Experiencia General: Tu tarea es analizar el documento proporcionado y extraer la información sobre los requisitos de experiencia solicitados. "
                    "Debes devolver únicamente un objeto JSON válido en el siguiente formato:\n\n"
                "Devuelve solo un arreglo JSON con la siguiente estructura exacta:\n\n"
                    "[\n"
                    "  {\n"
                    "    \"objeto\": \"Objeto solicitado del documento\",\n"
                    "  },\n"
                    "  {\n"
                    "    \"codigos_unspsc\": \"Codigos UNSPSC solicitados en el documento\",\n"
                    "  },\n"
                    "  \"indicadores_financieros\": {\n"
                    "    \"indice_de_liquidez\": float,  // Valor numérico del indice de liquidez solicitado\n"
                    "    \"indice_de_endeudamiento\": float,  // Valor numérico del indice de endeudamiento solicitado\n"
                    "    \"razon_cobertura_intereses\": float,  // Valor numérico de la razón de cobertura de intereses solicitada\n"
                    "    \"rentabilidad_patrimonio\": float,  // Valor numérico de la rentabilidad del patrimonio soliictado\n"
                    "    \"rentabilidad_activo\": float,  // Valor numérico de la rentabilidad del activo solicitado\n"
                    "  },\n"
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
                    "  ...\n"
                    "]\n\n"
                    "No incluyas explicaciones ni texto adicional. "
                    "Devuelve exclusivamente el JSON con los indicadores comparados."
            )
        },
        {
            'role': 'user',
            'content': [
                {'type': 'input_file', 'file_id': archivo.id},
                {'type': 'input_text',
                 'text': ("Analiza el documento y devuelve el JSON solicitado.")}
            ]
        }
    ]
).output_text.strip()
def parse_response(response: str):

    # 1. Limpiar marcas de código
    clean_text = re.sub(r"```(?:json)?\n?", "", response)
    clean_text = re.sub(r"\n?```", "", clean_text).strip()

    data = {}

    # 2. Intentar parsear directo
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError:
        # 3. Buscar bloques { ... }
        bloques = re.findall(r'\{.*?\}', clean_text, re.DOTALL)
        for b in bloques:
            try:
                obj = json.loads(b)
                if isinstance(obj, dict):
                    data.update(obj)
            except json.JSONDecodeError:
                continue

    # 4. Si sigue siendo lista, unir en dict
    if isinstance(data, list):
        merged = {}
        for item in data:
            if isinstance(item, dict):
                merged.update(item)
        data = merged

    # 5. Asegurarse que siempre sea dict
    if not isinstance(data, dict):
        data = {}

    return data


data = parse_response(response)

objeto = data.get("objeto", "")
codigos_unspsc = data.get("codigos_unspsc", [])
ind_financ = data.get("indicadores_financieros", {})
indice_liquidez = ind_financ.get("indice_de_liquidez")
indice_endeudamiento = ind_financ.get("indice_de_endeudamiento")
razon_cobertura = ind_financ.get("razon_cobertura_intereses")
rentabilidad_patrimonio = ind_financ.get("rentabilidad_patrimonio")
rentabilidad_activo = ind_financ.get("rentabilidad_activo")

experiencia = data.get("experiencia_general", {})
presupuesto_oficial = experiencia.get("presupuesto_oficial")
iva = experiencia.get("IVA", False)
numero_contratos = experiencia.get("numero_contratos", 1)
condicion_experiencia = experiencia.get("condicion_experiencia", "minimo")
porcentaje = experiencia.get("porcentaje", 1.0)
valor_smlmv = experiencia.get("valor_smlmv", 0)
codigos = experiencia.get("codigos", [])
antiguedad = experiencia.get("antiguedad", 0)


# ----- IMPRESIÓN ESTRUCTURADA DE RESULTADOS -----

print("\n***** RESULTADOS DE LA LICITACIÓN *****\n")

# 1. Objeto
print("1. OBJETO:")
print(f"   {objeto}\n")

# 2. Códigos UNSPSC
print("2. CÓDIGOS UNSPSC:")
print(f"   - {codigos_unspsc}\n")

# 3. Indicadores Financieros
print("3. INDICADORES FINANCIEROS:")
print(f"   Índice de Liquidez: {indice_liquidez}")
print(f"   Índice de Endeudamiento: {indice_endeudamiento}")
print(f"   Razón de Cobertura de Intereses: {razon_cobertura}")
print(f"   Rentabilidad del Patrimonio: {rentabilidad_patrimonio}")
print(f"   Rentabilidad del Activo: {rentabilidad_activo}\n")

# 4. Experiencia General
print("4. EXPERIENCIA GENERAL:")
print(f"   Presupuesto Oficial: {presupuesto_oficial}")
print(f"   Valor en SMLMV: {valor_smlmv}")
print(f"   Incluye IVA: {iva}")
print(f"   Número de Contratos: {numero_contratos}")
print(f"   Condición de Experiencia: {condicion_experiencia}")
print(f"   Porcentaje: {porcentaje}")
print(f"   Antigüedad (años): {antiguedad}")

print("   Códigos UNSPSC solicitados en experiencia:")
print(codigos)

print("\n***** FIN DE RESULTADOS *****\n")
