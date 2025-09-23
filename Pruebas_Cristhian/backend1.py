# procesador.py
from openai import OpenAI
import mysql.connector
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import re, json
import os
from pydantic import BaseModel, Field

# Crear cliente de OpenAI
client = OpenAI(api_key="")

# Clase de conexion MySQL
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

# Evaluador
def evaluar_licitacion(filepath):
    db = ConexionMySQL()
    lista_exp = db.consultar("SELECT objeto FROM experiencia;")
    lista_cod_base = db.consultar("SELECT codigo_unspsc FROM codigos_unspsc;")
    lista_indic = db.consultar("SELECT descripcion, valor FROM indicadores_financieros;")
    lista_cod = set(str(c)[:6] + '00' for c in lista_cod_base)

    # Subir archivo
    archivo = client.files.create(file=open(filepath, "rb"), purpose="user_data")

    # ****** OBJETO ******
    array_exp = []
    for texto in lista_exp:
        emb = client.embeddings.create(model="text-embedding-3-large", input=texto)
        array_exp.append(emb.data[0].embedding)

    # Extraer objeto
    objeto = client.responses.create(
        model='gpt-4o-mini',
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
    print(f'Objeto: {objeto}')

    emb_objeto = client.embeddings.create(model="text-embedding-3-large", input=objeto)
    simil = cosine_similarity([np.array(emb_objeto.data[0].embedding)], array_exp)[0]
    top_indices = simil.argsort()[-3:][::-1]

    # Lista para almacenar los textos más similares
    text_similares = []
    sim_ponderada = 0
    ponderaciones = [0.7, 0.2, 0.1]
    UMBRAL_OBJETO = 0.55  # umbral ponderado que ya usas
    UMBRAL_OBJETO_MIN = 0.40  # umbral absoluto de descarte

    # Score ponderado
    sim_prom = sum(simil[idx] * ponderaciones[i] for i, idx in enumerate(top_indices)) / sum(ponderaciones)
    mejor_match = max(simil)  # el score más alto encontrado

    # Validación doble:
    if sim_prom >= UMBRAL_OBJETO and mejor_match >= UMBRAL_OBJETO_MIN:
        cumple_obj = "SI"
    else:
        cumple_obj = "NO"

    print(f'Promedio objeto: {sim_prom}')

    # ****** CODIGOS UNSPSC ******
    # Extraer codigos UNSPSC
    codigos = client.responses.create(
        model='gpt-5',
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
                    {"type": "input_file", "file_id": archivo.id},
                    {"type": "input_text", "text": "Extrae todos los códigos UNSPSC del documento cargado."}
                ]
            }
        ]
    ).output_text

    clean_text = re.sub(r"```(?:json)?\n?", "", codigos)  # elimina ```json o ``` + salto
    clean_text = re.sub(r"\n?```", "", clean_text)  # elimina cierre final ```
    clean_text = clean_text.strip()

    lista_cod8 = json.loads(clean_text)
    lista_cod_solic = set(c[:6] + '00' for c in lista_cod8)

    encontrados = []
    no_encontrados = []

    for codigo in lista_cod_solic:
        if codigo in lista_cod:
            encontrados.append(codigo)
        else:
            no_encontrados.append(codigo)

    porcentaje_encontrados = (len(encontrados) / len(lista_cod_solic)) if len(lista_cod_solic) > 0 else 0
    print(f'Encontrados: {encontrados}\n No encontrados: {no_encontrados}')

    cumple_unspsc = "SI" if porcentaje_encontrados > 0.75 else "NO"

    # ****** INDICADORES FINANCIEROS ******
    # Extraer indicadores financieros
    resp_ind = client.responses.create(
        model='gpt-5',
        input=[
            {
                'role': 'system',
                'content': (
                    "Eres un asistente experto en análisis financiero para licitaciones. "
                    "Tu tarea es extraer los indicadores financieros de los documentos proporcionados (Indice de Liquidez, Indice de Endeudamiento, Razon de Cobertura de Intereses, Rentabilidad del Patrimonio y Rentabilidad del Activo)"
                    "asegurarte de estandarizar todos los valores (elimina símbolos como '$', '%', comas, puntos de miles o caracteres no numéricos) "
                    "y convertir porcentajes a decimales cuando corresponda. "
                    "Luego compara cada indicador solicitado con el correspondiente de la base INSITEL,"
                    "tener en cuenta cuando se pide Mayor que ó Menor qué, algunas licitaciones solicitan los valores en formato de mínimo y máximo, en eso casos recordar que cuando nos pide mínimo están solicitando un valor mayor o igual y cuando solicitan máximo se solicita un valor menor o igual."
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
                        f"Analiza los indicadores financieros entregados en el archivo base INSITEL {lista_indic}"
                        "y compáralos con los indicadores solicitados en el archivo de licitación. "
                        "Ten en cuenta la conversión de porcentajes a decimales."
                    )}
                ]
            }
        ]
    ).output_text.strip()

    class Indicadores(BaseModel):
        Indicador: str
        Valor_Indicador_Base_INSITEL: float = Field(alias="Valor Indicador Base INSITEL")
        Valor_Indicador_Solicitado: float = Field(alias="Valor Indicador Solicitado")
        Cumplimos: bool

    # Función para extraer indicadores en formato lista
    def extract_indic(output):
        # Limpiar delimitadores de bloque
        if output.startswith("```json"):
            output = output.replace("```json", "").strip()
        if output.startswith("```"):
            output = output.replace("```", "").strip()
        if output.endswith("```"):
            output = output[:-3].strip()

        try:
            lista_dicts = json.loads(output)
            indicadores = [Indicadores(**item) for item in lista_dicts]

            # Lista con nombre del indicador y valor solicitado
            indic_financieros = [
                (ind.Indicador, "CUMPLE" if ind.Cumplimos else "NO CUMPLE")
                #(ind.Indicador, ind.Valor_Indicador_Solicitado, "CUMPLE" if ind.Cumplimos else "NO CUMPLE")
                for ind in indicadores
            ]
            return indic_financieros
        except Exception as e:
            print("Error al convertir la salida en objetos Indicadores:", e)

    # *********** PRUEBA VALOR INDICADOR:
    def extr_indic(output):
        # Limpiar delimitadores de bloque
        if output.startswith("```json"):
            output = output.replace("```json", "").strip()
        if output.startswith("```"):
            output = output.replace("```", "").strip()
        if output.endswith("```"):
            output = output[:-3].strip()

        try:
            lista_dicts = json.loads(output)
            indicadores = [Indicadores(**item) for item in lista_dicts]

            # Lista con nombre del indicador y valor solicitado
            indic_financieros = [
                #(ind.Indicador, "CUMPLE" if ind.Cumplimos else "NO CUMPLE")
                (ind.Indicador, ind.Valor_Indicador_Solicitado, "CUMPLE" if ind.Cumplimos else "NO CUMPLE")
                for ind in indicadores
            ]
            return indic_financieros
        except Exception as e:
            print("Error al convertir la salida en objetos Indicadores:", e)
    # ***********

    db.cerrar()
    # Indicadores financieros procesados
    indicadores_financieros = extract_indic(resp_ind)
    ind = extr_indic(resp_ind)
    print(f'Indicadores: {ind}')

    indicador = {
        nombre: "Cumple" if estado == "CUMPLE" else "No Cumple"
        for nombre, estado in indicadores_financieros
        #for nombre, estado, valor in indicadores_financieros
    }

    # Calcular promedio de cumplimiento
    total_indicadores = len(indicador)
    cumplen = sum(1 for estado in indicador.values() if estado == "Cumple")
    porcentaje_cumplen = cumplen / total_indicadores if total_indicadores > 0 else 0

    cumple_indic = "SI" if porcentaje_cumplen > 0.75 else "NO"

     #Conclusión (lógica básica, puedes afinarla)
    conclusion = (
        "Revisar licitación"
        if cumple_obj == "SI" and cumple_unspsc == "SI" and cumple_indic == 'SI' else "Descartar Licitación"
    )

    # Armar resultado final
    resultado = {
        "objeto": "Si" if cumple_obj == "SI" else "No",
        "unspsc_cumple": "Si" if cumple_unspsc == "SI" else "No",
        "unspsc_incumplidos": ", ".join(no_encontrados),
        "indicadores": {
            nombre: "Cumple" if estado == "CUMPLE" else "No Cumple"
            for nombre, estado in indicadores_financieros
            #for nombre, estado, valor in indicadores_financieros
        },
        "conclusion": conclusion
    }

    return resultado

'''
if __name__ == "__main__":
    resultado = evaluar_licitacion("PruebaLicitacion2.pdf")
    print("Resultado final:")
    print(resultado)
'''