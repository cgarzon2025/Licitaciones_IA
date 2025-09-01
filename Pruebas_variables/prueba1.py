# ============================================================
# LIBRERÍAS NECESARIAS
# ============================================================
from openai import OpenAI
import mysql.connector
import re, json
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional

# ============================================================
# LLAMADO A LLAVE DE OPEN AI
# ============================================================
client = OpenAI(api_key="")  # <-- Reemplazar con tu clave real

# ============================================================
# CLASE PARA CONEXIÓN A DB MYSQL
# ============================================================
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

# ============================================================
# ESQUEMAS Pydantic PARA VALIDAR RESPUESTA JSON
# ============================================================
class IndicadoresFinancieros(BaseModel):
    indice_de_liquidez: Optional[float] = None
    indice_de_endeudamiento: Optional[float] = None
    razon_cobertura_intereses: Optional[float] = None
    rentabilidad_patrimonio: Optional[float] = None
    rentabilidad_activo: Optional[float] = None

class ExperienciaGeneral(BaseModel):
    presupuesto_oficial: Optional[float] = None
    IVA: bool = False
    numero_contratos: int = 1
    condicion_experiencia: str = "minimo"
    porcentaje: float = 1.0
    valor_smlmv: float = 0
    codigos: List[str] = []
    antiguedad: int = 0

class Licitacion(BaseModel):
    objeto: str = ""
    codigos_unspsc: List[str] = []
    indicadores_financieros: IndicadoresFinancieros
    experiencia_general: ExperienciaGeneral

# ============================================================
# PARSE RESPONSE (mantiene compatibilidad con prompt actual)
# ============================================================
def parse_response(response: str) -> dict:
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

    # 4. Si es lista, combinar en un dict
    if isinstance(data, list):
        merged = {}
        for item in data:
            if isinstance(item, dict):
                merged.update(item)
        data = merged

    # 5. Asegurarse que sea dict
    if not isinstance(data, dict):
        data = {}

    return data

def normalize_data(data: dict) -> dict:
    """
    Reorganiza la salida del modelo para que siempre tenga
    'indicadores_financieros' y 'experiencia_general'.
    """
    # Si los indicadores vinieron "sueltos" en la raíz del JSON → los agrupamos
    if "indicadores_financieros" not in data:
        posibles = {
            "indice_de_liquidez",
            "indice_de_endeudamiento",
            "razon_cobertura_intereses",
            "rentabilidad_patrimonio",
            "rentabilidad_activo",
        }
        encontrados = {k: data.pop(k) for k in list(data.keys()) if k in posibles}
        data["indicadores_financieros"] = encontrados

    # Si falta experiencia_general → ponemos dict vacío
    if "experiencia_general" not in data:
        data["experiencia_general"] = {}

    return data

# ============================================================
# FUNCIÓN PRINCIPAL PARA EXTRAER VARIABLES
# ============================================================
def extraer_variables(file_path: str) -> Optional[Licitacion]:
    # Subir archivo
    archivo = client.files.create(file=open(file_path, "rb"), purpose="user_data")

    # Llamada al modelo
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
                    "    \"IVA\": boolean,  // True si menciona que el presupuesto incluye IVA, False en caso contrario\n"
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

    # Parsear respuesta
    raw_data = parse_response(response)
    normalized_data = normalize_data(raw_data)

    # Validar con Pydantic
    try:
        licitacion = Licitacion.model_validate(normalized_data)
        return licitacion
    except ValidationError as e:
        print("❌ Error validando JSON:", e)
        print("➡️ Datos recibidos:", normalized_data)  # Debug
        return None


# ============================================================
# IMPRESIÓN ESTRUCTURADA DE RESULTADOS
# ============================================================
def imprimir_resultados(licitacion: Licitacion):
    print("\n***** RESULTADOS DE LA LICITACIÓN *****\n")

    print("1. OBJETO:")
    print(f"   {licitacion.objeto}\n")

    print("2. CÓDIGOS UNSPSC:")
    print(f"   - {licitacion.codigos_unspsc}\n")

    print("3. INDICADORES FINANCIEROS:")
    print(f"   Índice de Liquidez: {licitacion.indicadores_financieros.indice_de_liquidez}")
    print(f"   Índice de Endeudamiento: {licitacion.indicadores_financieros.indice_de_endeudamiento}")
    print(f"   Razón de Cobertura de Intereses: {licitacion.indicadores_financieros.razon_cobertura_intereses}")
    print(f"   Rentabilidad del Patrimonio: {licitacion.indicadores_financieros.rentabilidad_patrimonio}")
    print(f"   Rentabilidad del Activo: {licitacion.indicadores_financieros.rentabilidad_activo}\n")

    print("4. EXPERIENCIA GENERAL:")
    print(f"   Presupuesto Oficial: {licitacion.experiencia_general.presupuesto_oficial}")
    print(f"   Valor en SMLMV: {licitacion.experiencia_general.valor_smlmv}")
    print(f"   Incluye IVA: {licitacion.experiencia_general.IVA}")
    print(f"   Número de Contratos: {licitacion.experiencia_general.numero_contratos}")
    print(f"   Condición de Experiencia: {licitacion.experiencia_general.condicion_experiencia}")
    print(f"   Porcentaje: {licitacion.experiencia_general.porcentaje}")
    print(f"   Antigüedad (años): {licitacion.experiencia_general.antiguedad}")
    print("   Códigos UNSPSC solicitados en experiencia:")
    print(licitacion.experiencia_general.codigos)

    print("\n***** FIN DE RESULTADOS *****\n")

# ============================================================
# EJECUCIÓN
# ============================================================
if __name__ == "__main__":
    licitacion = extraer_variables("PruebaLicitacion2.pdf")
    if licitacion:
        imprimir_resultados(licitacion)
