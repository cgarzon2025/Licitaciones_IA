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

# FUNCION PRINCIPAL
def evaluar_licitacion():
    # ALMACENAR LISTAS DE DATOS NECESARIOS
    db = ConexionMySQL()
    lista_experiencia = db.consultar("SELECT consecutivo, objeto, smmlv FROM experiencia;")
    lista_codigos = db.consultar("SELECT codigo_unspsc FROM codigos_unspsc;")
    lista_indicadores = db.consultar("SELECT descripcion, valor FROM indicadores_financieros;")

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
    #print(f'Objeto: {objeto}')

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
    ponderaciones = [0.7, 0.2, 0.1]

    for i, idx in enumerate(top_indices):
        text_similares.append(lista_experiencia[idx][1])
        #print(f'Experiencia {lista_experiencia[idx][0]}: {text_similares[i]}')
        sim_ponderada += simil[idx] * ponderaciones[i]
    sim_prom = sim_ponderada / sum(ponderaciones)
    #print(f'Promedio objeto: {sim_prom}')

    # OBTENER CONTRATOS MÁS SIMILARES POR CONSECUTIVO
    contratos_similares = [lista_experiencia[idx][0] for idx in top_indices]

    cumple_obj = "SI" if sim_prom >= 0.55 else "NO"

    # ****** CODIGOS UNSPSC ******
    # EXTRAER CODIGOS UNSPSC
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

    # LIMPIAR CARACTERES BASURA
    clean_text = re.sub(r"```(?:json)?\n?", "", codigos)  # elimina ```json o ``` + salto
    clean_text = re.sub(r"\n?```", "", clean_text)  # elimina cierre final ```
    clean_text = clean_text.strip()
    lista_cod8 = json.loads(clean_text)

    # LIMITAR CODIGO A 8 BITS Y GARANTIZAR LOS ULTIMOS 2 BITS COMO '00'
    lista_cod_solic = set(c[:6] + '00' for c in lista_cod8)
    #print(lista_cod_solic)

    # BUSQUEDA DE CODIGOS SOLICITADOS EN BASE DE DATOS
    encontrados = []
    no_encontrados = []
    for codigo in lista_cod_solic:
        if codigo in lista_codigos:
            encontrados.append(codigo)
        else:
            no_encontrados.append(codigo)
    porcentaje_encontrados = (len(encontrados) / len(lista_cod_solic)) if len(lista_cod_solic) > 0 else 0
    #print(f'Encontrados: {encontrados}\n No encontrados: {no_encontrados}')

    cumple_unspsc = "SI" if porcentaje_encontrados > 0.75 else "NO"

    # ****** INDICADORES FINANCIEROS ******
    # EXTRAER INDICADORES
    resp_ind = client.responses.create(
        model='gpt-4o',
        input=[
            {
                'role': 'system',
                'content': (
                    "Eres un asistente experto en análisis financiero para licitaciones. "
                    "Tu tarea es extraer los indicadores financieros de los documentos proporcionados ('Indice de Liquidez', 'Indice de Endeudamiento', 'Razón de Cobertura de Interes' 'Rentabilidad del Patrimonio' y 'Rentabilidad del Activo'), "
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
                        f"Analiza los indicadores financieros entregados en el archivo base INSITEL {lista_indicadores}"
                        "y compáralos con los indicadores solicitados en el archivo de licitación. "
                        "Ten en cuenta la conversión de porcentajes a decimales."
                    )}
                ]
            }
        ]
    ).output_text.strip()

    # MODELO DE DATOS CON PYDANTIC
    class Indicadores(BaseModel):
        Indicador: str
        Valor_Indicador_Base_INSITEL: float = Field(alias="Valor Indicador Base INSITEL")
        Valor_Indicador_Solicitado: float = Field(alias="Valor Indicador Solicitado")
        Cumplimos: bool

    # FUNCION PARA EXTRAER INDICADORES EN LISTA
    def extract_indic(output):
        # SE HACE LIMPIEZA DE LIMITADORES DE BLOQUE
        if output.startswith("```json"):
            output = output.replace("```json", "").strip()
        if output.startswith("```"):
            output = output.replace("```", "").strip()
        if output.endswith("```"):
            output = output[:-3].strip()

        try:
            lista_dicts = json.loads(output)
            indicadores = [Indicadores(**item) for item in lista_dicts]

            # LISTA CON NOMBRE Y VALOR DE INDICADOR SOLICITADO
            indic_financieros = [
                (ind.Indicador, ind.Valor_Indicador_Solicitado, "CUMPLE" if ind.Cumplimos else "NO CUMPLE")
                for ind in indicadores
            ]
            return indic_financieros
        except Exception as e:
            print("Error al convertir la salida en objetos Indicadores:", e)
    #print(f'Indicadores:\n{extract_indic(resp_ind)} \n {type(extract_indic(resp_ind))}')

    # SE TRAE LOS INDICADORES PROCESADOS
    indicadores_financieros = extract_indic(resp_ind)

    # SE CREA DICCIONARIO CON NOMBRE Y ESTADO DE INDICE FINANCIERO
    indicador = {
        nombre: "Cumple" if estado == "CUMPLE" else "No Cumple"
        for nombre, valor, estado in indicadores_financieros
    }

    # CALCULAR PROMEDIO DE CUMPLIMIENTO
    cumplen = sum(1 for estado in indicador.values() if estado == "Cumple")
    porcentaje_cumplen = cumplen / len(indicador) if len(indicador) > 0 else 0

    cumple_indic = "SI" if porcentaje_cumplen > 0.75 else "NO"

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
    #print(f'Contratos que cumplen con el 100% de los códigos requeridos: {contratos_validos}')

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
        "Vale la pena Revisar la Licitación" if cumple_obj == "SI" and cumple_unspsc == "SI" and cumple_indic == 'SI' and cumple_smlmv == True else "Descartar Licitación")

    print('***** RESULTADO FINAL *****\n')

    # 1. OBJETO
    print('1. OBJETO:')
    print(f'Cumple con el objeto solicitado: {cumple_obj}\n')

    # 2. Códigos UNSPSC
    print('2. CODIGOS UNSPSC:')
    print(f'Cumple con los códigos UNSPSC: {cumple_unspsc}')
    print(f'Códigos no encontrados: {no_encontrados}\n')

    # 3. Indicadores Financieros
    print('3. INDICADORES FINANCIEROS:')
    print(f'Indicadores evaluados:')
    for nombre, valor, estado in indicadores_financieros:
        print(f' - {nombre}: {valor} → {estado}')
    print(f'Cumple en total: {"SI" if cumple_indic == "SI" else "NO"}\n')

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
evaluar_licitacion()

