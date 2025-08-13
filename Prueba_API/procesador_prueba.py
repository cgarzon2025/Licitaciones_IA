#   ***** BACKEND PARA PROYECTO LICITACIONES CON IA *****

# LIBRERIAS NECESARIAS
from openai import OpenAI
import mysql.connector
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import re, json, os
from pydantic import BaseModel, Field

# LLAMADO A LLAVE DE OPEN AI
client = OpenAI(api_key="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")  # Reemplazar con tu clave real

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
    lista_experiencia = db.consultar("SELECT objeto FROM experiencia;")
    lista_codigos = db.consultar("SELECT codigo_unspsc FROM codigos_unspsc;")
    lista_indicadores = db.consultar("SELECT descripcion, valor FROM indicadores_financieros;")

    # LISTA DE CODIGOS DE CADA CONTRATO
    lista_codigos_contrato = db.consultar("SELECT consecutivo, codigos_unspsc FROM contratos;")
    diccionario_contratos = {}
    for consecutivo, codigos in lista_codigos_contrato:
        if consecutivo not in diccionario_contratos:
            diccionario_contratos[consecutivo] = []
        diccionario_contratos[consecutivo].append(codigos)
    '''
    for consecutivo, codigos in diccionario_contratos.items():
        print(f'{consecutivo}:')
        for codigo in codigos:
            print(f'  - {codigo}')
    '''

    return True
evaluar_licitacion()
'''
# Evaluador
def evaluar_licitacion(filepath):
    db = ConexionMySQL()
    lista_exp = db.consultar("SELECT objeto FROM experiencia;")
    lista_cod_base = db.consultar("SELECT codigo_unspsc FROM codigos_unspsc;")
    lista_indic = db.consultar("SELECT descripcion, valor FROM indicadores_financieros;")
    cod = db.consultar("SELECT consecutivo, codigos_unspsc FROM contratos")

    def obtener_diccionario_contratos(db):
        query = "SELECT consecutivo, codigos_unspsc FROM contratos;"
        resultados = db.consultar(query)

        contratos_dict = {}
        for consecutivo, codigo in resultados:
            if consecutivo not in contratos_dict:
                contratos_dict[consecutivo] = []
            contratos_dict[consecutivo].append(codigo)

        return contratos_dict

    contratos_dict = obtener_diccionario_contratos(db)

    for consecutivo, codigos in contratos_dict.items():
        print(f"Contrato {consecutivo} tiene los siguientes códigos:")
        for codigo in codigos:
            print(f"  - {codigo}")


    lista_cod = set(str(c)[:6] + '00' for c in lista_cod_base)
    
    # Subir archivo
    archivo = client.files.create(file=open(filepath, "rb"), purpose="user_data")

    # ****** OBJETO ******
    array_exp = []
    for texto in lista_exp:
        emb = client.embeddings.create(model="text-embedding-3-small", input=texto)
        array_exp.append(emb.data[0].embedding)
        
    # Extraer objeto
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
    print(f'Objeto: {objeto}')

    emb_objeto = client.embeddings.create(model="text-embedding-3-small", input=objeto)
    simil = cosine_similarity([np.array(emb_objeto.data[0].embedding)], array_exp)[0]
    top_indices = simil.argsort()[-3:][::-1]

    # Lista para almacenar los textos más similares
    text_similares = []
    sim_ponderada = 0
    si2 = 0
    ponderaciones = [0.6, 0.3, 0.1]
    #print('PRUEBA 1')
    for i, idx in enumerate(top_indices):
        text_similares.append(lista_exp[idx])
        si2 += simil[idx]
        sim_ponderada += simil[idx] * ponderaciones[i]

    sim_prom = sim_ponderada / sum(ponderaciones)
    sim_prom2 = si2 / len(top_indices)
    print(f'Promedio objeto: {sim_prom2} _ {sim_prom}')

    cumple_obj = "SI" if sim_prom >= 0.55 else "NO"
    
    # ****** CODIGOS UNSPSC ******
    # Extraer codigos UNSPSC
    codigos = client.responses.create(
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
    lista_cod_solic = set(c[:6] + '' for c in lista_cod8)

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
        model='gpt-4o',
        input=[
            {
                'role': 'system',
                'content': (
                    "Eres un asistente experto en análisis financiero para licitaciones. "
                    "Tu tarea es extraer los indicadores financieros de los documentos proporcionados, "
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
    return True
if __name__ == "__main__":
    resultado = evaluar_licitacion("uploads/resumen_pliegos_1.pdf")
    print("Resultado final:")
    print(resultado)
    '''
