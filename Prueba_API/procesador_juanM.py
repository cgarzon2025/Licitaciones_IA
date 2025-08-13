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

    archivo = client.files.create(file=open('licitacion_prueba1.pdf', "rb"), purpose="user_data")

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
    return True
evaluar_licitacion()