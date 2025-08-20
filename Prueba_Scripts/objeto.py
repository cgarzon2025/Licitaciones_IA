from librerias_db_archivo import client, archivo, db, np, cosine_similarity

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
# EXTRAER OBJETO DE LICITACION
objeto_licitacion = extraer_objeto(archivo.id)
print(objeto_licitacion)
# EXTRAER LISTA DE EXPERIENCIA
lista_experiencia = db.consultar("SELECT consecutivo, objeto, smmlv FROM experiencia;")
# EVALUAR OBJETO:
resultado_objeto = evaluar_objeto(objeto_licitacion, lista_experiencia)
print(resultado_objeto)