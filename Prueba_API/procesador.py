# procesador.py
from openai import OpenAI
import mysql.connector
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import re, json, os

client = OpenAI(api_key="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")  # Reemplazar con tu clave real

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

    emb_objeto = client.embeddings.create(model="text-embedding-3-small", input=objeto)
    simil = cosine_similarity([np.array(emb_objeto.data[0].embedding)], array_exp)[0]
    top_indices = simil.argsort()[-3:][::-1]

    text_similares = []
    sim = 0
    count = 0
    for idx in top_indices:
        text_similares.append(lista_exp[idx])
        sim += simil[idx]
        count += 1
    sim_prom = sim / count

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
    lista_cod_solic = set(c[:6] + '00' for c in lista_cod8)

    encontrados = []
    no_encontrados = []

    for codigo in lista_cod_solic:
        if codigo in lista_cod:
            encontrados.append(codigo)
        else:
            no_encontrados.append(codigo)

    porcentaje_encontrados = (len(encontrados) / len(lista_cod_solic)) * 100 if len(lista_cod_solic) > 0 else 0
    #print(f'Encontrados: {encontrados}\n No encontrados: {no_encontrados}')

    cumple_unspsc = "CUMPLE" if porcentaje_encontrados > 0.65 else "NO CUMPLE"

    # Extraer indicadores financieros
    prompt_ind = """Compara los indicadores financieros solicitados en la licitación con los siguientes valores: 
    """ + str(lista_indic) + ". ¿INSITEL cumple los requisitos financieros? Responde solo con 'Sí' o 'No'."

    resp_ind = client.responses.create(
        model='gpt-4o',
        input=[
            {"role": "user", "content": [
                {"type": "input_file", "file_id": archivo.id},
                {"type": "input_text", "text": prompt_ind}
            ]}
        ]
    ).output_text.strip()

    cumple_ind = "sí" in resp_ind.lower()

    conclusion = "CUMPLE" if sim_prom > 0.75 and cumple_unspsc and cumple_ind else "NO CUMPLE"

    db.cerrar()
    return {
        "experiencia_similitud": round(sim_prom, 3),
        "unspsc_cumple": cumple_unspsc,
        "indicadores_cumple": cumple_ind,
        "conclusion": conclusion
    }

'''
if __name__ == "__main__":
    resultado = evaluar_licitacion("uploads/licitacion_prueba2.pdf")
    print("Resultado final:")
    print(resultado)
'''