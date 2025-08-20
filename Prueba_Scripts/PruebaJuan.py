from openai import OpenAI
import mysql.connector

# LLAMADO A LLAVE DE OPEN AI
client = OpenAI(api_key="")
# SUBIR ARCHIVO
archivo = client.files.create(file=open('PruebaLicitacion1.pdf', "rb"), purpose="user_data")
# PROMPT GENERAL CON ESTEROIDES
prompt_general = client.responses.create(
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
print(prompt_general)