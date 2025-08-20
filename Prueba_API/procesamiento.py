#   ***** BACKEND PARA PROYECTO LICITACIONES CON IA *****

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

# FUNCION PARA EXTRAER EL OBJETO
def extraer_objeto(file_id: str) -> str:
    response = client.responses.create(
        model='gpt-4o',
        input=[
            {
                'role': 'user',
                'content': [
                    {'type': 'input_file', 'file_id': file_id},
                    {'type': 'input_text', 'text': (
                        'Extrae el objeto del documento, busca únicamente el objeto como tal. '
                        'No incluyas explicaciones ni texto adicional, solo el objeto.'
                    )}
                ]
            }
        ]
    )
    return response.output_text.strip()

# FUNCION PARA EVALUAR EL OBJETO
def evaluar_objeto(objeto: str, lista_experiencia: list) -> dict:
    """
    Evalúa si el objeto de la licitación es compatible con la experiencia de la empresa.

    Parámetros:
    - objeto: texto del objeto extraído de la licitación
    - lista_experiencia: lista de tuplas (consecutivo, objeto, smmlv) de la DB

    Retorna:
    - dict con similitud, contratos similares y decisión (SI/NO)
    """
    # Embeddings experiencias
    vectores_exp = []
    for consecutivo, objeto_exp, smmlv in lista_experiencia:
        emb = client.embeddings.create(
            model="text-embedding-3-small",
            input=objeto_exp
        )
        vectores_exp.append(np.array(emb.data[0].embedding))

    # Embedding del objeto licitación
    emb_objeto = client.embeddings.create(
        model="text-embedding-3-small",
        input=objeto
    )
    vec_objeto = np.array(emb_objeto.data[0].embedding)

    # Comparación coseno
    simil = cosine_similarity([vec_objeto], vectores_exp)[0]
    top_indices = simil.argsort()[-3:][::-1]

    # Top 3 experiencias más similares
    text_similares = [lista_experiencia[idx][1] for idx in top_indices]
    contratos_similares = [lista_experiencia[idx][0] for idx in top_indices]

    # Similitud ponderada
    ponderaciones = [0.7, 0.2, 0.1]
    sim_ponderada = sum(simil[idx] * ponderaciones[i] for i, idx in enumerate(top_indices))
    sim_prom = sim_ponderada / sum(ponderaciones)

    cumple = "SI" if sim_prom >= 0.55 else "NO"

    return {
        "cumple_objeto": cumple,
        "similitud_promedio": sim_prom,
        "contratos_similares": contratos_similares,
        "textos_similares": text_similares
    }

# FUNCION PARA EXTRAER LOS CODIGOS UNSPSC
def extraer_codigos_unspsc(file_id: str) -> list[str]:
    """
    Extrae todos los códigos UNSPSC del archivo cargado en OpenAI.
    Devuelve una lista de códigos de 8 dígitos (strings).
    """
    resp = client.responses.create(
        model='gpt-4o',
        input=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente experto en análisis de documentos técnicos. "
                    "Tu tarea es identificar y extraer todos los códigos UNSPSC presentes en el contenido que se te proporcione. "
                    "Los códigos UNSPSC pueden estar escritos de forma completa (8 dígitos seguidos), segmentada (por ejemplo: 43 22 25 01), "
                    "o distribuidos en tablas con celdas vacías, lo que implica que los valores deben heredarse de filas anteriores para formar un código completo. "
                    "Si un código tiene solo segmento, familia y clase (6 dígitos completos), complétalo siempre con dos ceros al final para formar un código de 8 dígitos. "
                    "Solo extrae códigos que tengan al menos 6 dígitos completos con valores distintos de cero. "
                    "Descarta códigos incompletos o códigos que solo tengan segmento o segmento + familia (por ejemplo: 41000000 o 43210000). "
                    "Reconstruye cada código UNSPSC como una cadena de 8 dígitos. "
                    "Devuelve el resultado como una lista JSON simple de cadenas, donde cada cadena es un código UNSPSC extraído. "
                    "No incluyas descripciones, explicaciones ni texto adicional fuera del JSON. Solo responde con el JSON solicitado."
                )
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": file_id},
                    {"type": "input_text", "text": "Extrae todos los códigos UNSPSC del documento cargado."}
                ]
            }
        ]
    ).output_text

    # Limpieza de posibles ```json
    clean_text = re.sub(r"```(?:json)?\n?", "", resp)
    clean_text = re.sub(r"\n?```", "", clean_text).strip()

    try:
        lista_codigos = json.loads(clean_text)
    except Exception as e:
        print("Error al parsear JSON de UNSPSC:", e)
        lista_codigos = []

    # Normalizar → siempre 8 dígitos y con '00' en últimos 2 si son clase
    lista_cod8 = list(set(c[:6] + '00' for c in lista_codigos if len(c) >= 6))

    return lista_cod8

# FUNCION PARA EVALUAR LOS CODIGOS UNSPSC EXTRAIDOS VS LA BASE DE DATOS
def evaluar_codigos_unspsc(codigos_extraidos: list[str], lista_codigos_db: list[str]) -> dict:
    """
    Compara los códigos extraídos con los códigos de la base INSITEL.

    Retorna un dict con encontrados, no encontrados, porcentaje de cumplimiento y decisión.
    """
    encontrados = []
    no_encontrados = []

    for codigo in codigos_extraidos:
        if codigo in lista_codigos_db:
            encontrados.append(codigo)
        else:
            no_encontrados.append(codigo)

    porcentaje_encontrados = (len(encontrados) / len(codigos_extraidos)) if codigos_extraidos else 0
    cumple = "SI" if porcentaje_encontrados >= 0.75 else "NO"

    return {
        "cumple_unspsc": cumple,
        "codigos_extraidos": codigos_extraidos,
        "encontrados": encontrados,
        "no_encontrados": no_encontrados,
        "porcentaje_encontrados": porcentaje_encontrados
    }

# FUNCION PARA EXTRAER LOS INDICADORES FINANCIEROS
# MODELO DE DATOS
class Indicadores(BaseModel):
    Indicador: str
    Valor_Indicador_Base_INSITEL: float = Field(alias="Valor Indicador Base INSITEL")
    Valor_Indicador_Solicitado: float = Field(alias="Valor Indicador Solicitado")
    Cumplimos: bool
def extraer_indicadores_licitacion(archivo, lista_indicadores):
    resp_ind = client.responses.create(
        model='gpt-4o',
        input=[
            {
                'role': 'system',
                'content': (
                    "Eres un asistente experto en análisis financiero para licitaciones. "
                    "Tu tarea es extraer los indicadores financieros de los documentos proporcionados ('Indice de Liquidez', 'Indice de Endeudamiento', 'Razón de Cobertura de Interes' 'Rentabilidad del Patrimonio' y 'Rentabilidad del Activo', "
                    "asegurarte de estandarizar todos los valores (elimina símbolos como '$', '%', comas, puntos de miles o caracteres no numéricos) "
                    "y convertir porcentajes a decimales cuando corresponda. "
                    "Luego compara cada indicador solicitado con el correspondiente de la base INSITEL,"
                    "tener en cuenta cuando se pide Mayor que ó Menor qué, algunas licitaciones solicitan los valores en formato de Mínimo ó Máximo, en eso casos recordar que cuando nos pide mínimo están solicitando un valor mayor o igual y cuando solicitan máximo se solicita un valor menor o igual."
                    "Devuelve solo un arreglo JSON con la siguiente estructura exacta:\n\n"
                    "[\n"
                    "  {\n"
                    "    \"Indicador\": \"Nombre del indicador solicitado\",\n"
                    "    \"Valor Indicador Base INSITEL\": indice_insitel,\n"
                    "    \"Valor Indicador Solicitado\": indice_solicitado,\n"
                    "    \"Cumplimos\": true/false,\n"
                    "    \"Valor Faltante\": Si Cumplimos==false => valor_obtenido - valor_db\n"
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
                    {'type': 'input_text', 'text': (
                        f"Analiza los indicadores financieros entregados en el archivo base INSITEL {lista_indicadores}"
                        "y compáralos con los indicadores solicitados en el archivo de licitación. "
                        "Ten en cuenta la conversión de porcentajes a decimales."
                    )}
                ]
            }
        ]
    ).output_text.strip()

    # Limpieza de delimitadores de bloque y parseo JSON
    if resp_ind.startswith("```json"):
        resp_ind = resp_ind.replace("```json", "").strip()
    if resp_ind.startswith("```"):
        resp_ind = resp_ind.replace("```", "").strip()
    if resp_ind.endswith("```"):
        resp_ind = resp_ind[:-3].strip()

    try:
        lista_dicts = json.loads(resp_ind)
        indicadores = [Indicadores(**item) for item in lista_dicts]
        return [
            (ind.Indicador, ind.Valor_Indicador_Solicitado, "CUMPLE" if ind.Cumplimos else "NO CUMPLE")
            for ind in indicadores
        ]
    except Exception as e:
        print("Error al convertir la salida en objetos Indicadores:", e)
        return []

# FUNCION PARA COMPARAR INDICADORES EXTRAIDOS VS LA BASE DE DATOS
def comparar_con_base(indicadores_financieros):
    """
    Devuelve un diccionario con:
      - Estado por indicador
      - Valor solicitado
      - Valor base
    Además calcula el porcentaje de cumplimiento y la decisión final.
    """
    indicador_estado = {}
    cumplen = 0

    for nombre, valor_solicitado, estado in indicadores_financieros:
        indicador_estado[nombre] = {
            "Estado": "Cumple" if estado == "CUMPLE" else "No Cumple",
            "Valor_Solicitado": valor_solicitado
            # "Valor_Base": valor_base  # si quieres agregarlo, puedes pasarlo también en la lista original
        }
        if estado == "CUMPLE":
            cumplen += 1

    porcentaje_cumplen = cumplen / len(indicador_estado) if len(indicador_estado) > 0 else 0
    cumple_indic = "SI" if porcentaje_cumplen > 0.75 else "NO"

    return indicador_estado, porcentaje_cumplen, cumple_indic

# VARIABLES AUXILIARES
db = ConexionMySQL()
# SUBIR ARCHIVO
archivo = client.files.create(file=open('PruebaLicitacion2.pdf', "rb"), purpose="user_data")
'''
# EXTRAER OBJETO DE LICITACION
objeto_licitacion = extraer_objeto(archivo.id)
# EXTRAER LISTA DE EXPERIENCIA
lista_experiencia = db.consultar("SELECT consecutivo, objeto, smmlv FROM experiencia;")
# EVALUAR OBJETO:
resultado_objeto = evaluar_objeto(objeto_licitacion, lista_experiencia)
print(resultado_objeto)
# EXTRAER LOS CODIGOS UNSPSC DE LICITACION
lista_cod_solic = extraer_codigos_unspsc(archivo.id)
# EXTRAER CODIGOS UNSPSC DE BASE DE DATOS
lista_codigos_db = db.consultar("SELECT codigo_unspsc FROM codigos_unspsc;")
resultado_unspsc = evaluar_codigos_unspsc(lista_cod_solic, lista_codigos_db)
print(resultado_unspsc)
'''
# EXTRAER INDICADORES DE BASE DE DATOS
lista_indicadores = db.consultar("SELECT descripcion, valor FROM indicadores_financieros;")
# EXTRAER INDICADORES FINANCIEROS DE LICITACION
indicadores_licitacion = extraer_indicadores_licitacion(archivo, lista_indicadores)
# EVALUAR INDICADORES FINANCIEROS
estado, porcentaje, decision = comparar_con_base(indicadores_licitacion)
print(estado)

