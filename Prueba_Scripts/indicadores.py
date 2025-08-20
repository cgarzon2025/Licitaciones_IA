from librerias_db_archivo import client, archivo, db, json, BaseModel, Field

# ****** INDICADORES FINANCIEROS ******
lista_indicadores = db.consultar("SELECT descripcion, valor FROM indicadores_financieros;")
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
print(f'Indicadores:\n{extract_indic(resp_ind)} \n {type(extract_indic(resp_ind))}')

# SE TRAE LOS INDICADORES PROCESADOS
indicadores_financieros = extract_indic(resp_ind)
print(indicadores_financieros)

# SE CREA DICCIONARIO CON NOMBRE Y ESTADO DE INDICE FINANCIERO
indicador = {
    nombre: "Cumple" if estado == "CUMPLE" else "No Cumple"
    for nombre, valor, estado in indicadores_financieros
}
print(indicador)

# CALCULAR PROMEDIO DE CUMPLIMIENTO
cumplen = sum(1 for estado in indicador.values() if estado == "Cumple")
porcentaje_cumplen = cumplen / len(indicador) if len(indicador) > 0 else 0

cumple_indic = "SI" if porcentaje_cumplen > 0.75 else "NO"
print(cumple_indic)
