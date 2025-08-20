from librerias_db_archivo import client, archivo, db, re, json

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
# EXTRAER LOS CODIGOS UNSPSC DE LICITACION
lista_cod_solic = extraer_codigos_unspsc(archivo.id)
# EXTRAER CODIGOS UNSPSC DE BASE DE DATOS
lista_codigos_db = db.consultar("SELECT codigo_unspsc FROM codigos_unspsc;")
resultado_unspsc = evaluar_codigos_unspsc(lista_cod_solic, lista_codigos_db)
print(resultado_unspsc)