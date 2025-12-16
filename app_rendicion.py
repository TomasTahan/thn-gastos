import os
from typing import TypedDict, Dict, Any, Optional, List

from dotenv import load_dotenv
load_dotenv()

# LangGraph / LangChain
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Structured output con Pydantic
from pydantic import BaseModel, Field
from enum import Enum

# Supabase
from supabase import create_client, Client

# ---------- Definimos el schema de salida ----------

class CategoriaGasto(str, Enum):
    """Categorías permitidas para gastos"""
    PEAJE = "PEAJE"
    MIGRAC = "MIGRAC"
    ADUANA = "ADUANA"
    TUNEL = "TUNEL"
    REPRESEN = "REPRESEN"
    SENASA = "SENASA"
    ISCAMEN = "ISCAMEN"
    GOMERIA = "GOMERIA"
    VARIOS = "VARIOS"

class GastoItem(BaseModel):
    categoria: CategoriaGasto = Field(..., description="Categoría del gasto. Debe ser una de las categorías permitidas")
    monto: float = Field(..., description="Monto del gasto")
    pais: str = Field(..., description="País del gasto. Ejemplos: Chile, Argentina, Brasil, Perú, Paraguay")

class ViaticoItem(BaseModel):
    monto: float = Field(..., description="Monto del viático")
    pais: str = Field(..., description="País del viático. Ejemplos: Chile, Argentina, Brasil, Perú, Paraguay")

class ChoferInfo(BaseModel):
    nombre_completo: str = Field(..., description="Nombre completo del chofer identificado")
    user_id: str = Field(..., description="ID del usuario/chofer en el sistema")

class ChoferMatchSchema(BaseModel):
    chofer: ChoferInfo = Field(..., description="Información del chofer identificado")

class RendicionSchema(BaseModel):
    numero_op: Optional[str] = Field(None, description="Número de operación de la rendición. Ubicado arriba a la derecha. Puede estar vacío (null)")
    fecha: Optional[str] = Field(None, description="Fecha de la rendición en formato dd/MM/yyyy. Ubicada arriba a la izquierda del formulario. Si no está visible, devolver null")
    chofer: str = Field(..., description="Nombre del chofer que realizó la rendición. Ubicado arriba a la izquierda. Siempre presente")
    gastos: List[GastoItem] = Field(default_factory=list, description="Listado de gastos de la rendición extraídos de la tabla GASTOS GENERALES")
    viaticos: List[ViaticoItem] = Field(default_factory=list, description="Listado de viáticos de la rendición extraídos de la tabla VIATICOS")
    chofer_info: Optional[ChoferInfo] = Field(None, description="Información del chofer identificado desde la base de datos")

# ---------- Estado del grafo ----------
class GraphState(TypedDict):
    image_url: str  # input
    conductor_description: Optional[str]  # descripción verbal del conductor
    result: Dict[str, Any]  # output final

# ---------- Cliente de Supabase ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- Modelo LLM (visión + structured output) ----------
MODEL_NAME = os.getenv("MODEL_NAME", "google/gemini-3-pro-preview")

llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model=MODEL_NAME,
    temperature=0,
)

# Empaquetamos el LLM para que DEVUELVA RendicionSchema (validado).
structured_llm = llm.with_structured_output(RendicionSchema)

# LLM para identificar chofer
chofer_match_llm = llm.with_structured_output(ChoferMatchSchema)

# ---------- Nodo: analizar imagen ----------
SYSTEM_PROMPT = (
    """
    Eres un agente especializado en extraer información estructurada de rendiciones de gastos.

    Tu trabajo es analizar imágenes de formularios de rendición y extraer datos específicos
    en formato JSON para procesamiento posterior.

    ## INSTRUCCIONES DETALLADAS:

    ### 1. NÚMERO DE OP (numero_op)
    - Ubicación: **Arriba a la derecha** del formulario
    - Campo: "NUMERO DE OP N°" o similar
    - **IMPORTANTE**: Este campo es OPCIONAL
    - Si el campo está vacío o no tiene valor, debes poner null
    - Si tiene valor, extraelo como string (ejemplo: "677524")

    ### 2. FECHA (fecha)
    - Ubicación: **Arriba del todo a la izquierda** del formulario
    - **IMPORTANTE**: Este campo es OPCIONAL
    - Si NO encuentras una fecha visible en el formulario, debes poner null
    - NO inventes una fecha. Si no está, pon null

    - **FORMATOS POSIBLES**:
      * Formato completo: "dd/MM/yyyy" o "d/M/yy" (ej: "24/11/2025" o "2/7/25")
      * Formato sin año: "dd/MM" o "d/M" (ej: "25/11" o "2/7")

    - **CONVERSIÓN DE FECHAS**:
      * SIEMPRE convierte al formato dd/MM/yyyy
      * Si la fecha NO tiene año, usa el año actual que te proporciono en el contexto
      * Si la fecha tiene año de 2 dígitos (ej: 25), conviértelo a 4 dígitos (ej: 2025)
      * Asegúrate de que el día y mes tengan 2 dígitos con cero a la izquierda si es necesario

    - **Ejemplos de conversión**:
      * "24/11/25" → "24/11/2025" (año de 2 dígitos)
      * "01/12/24" → "01/12/2024" (año de 2 dígitos)
      * "15-03-25" → "15/03/2025" (con guiones)
      * "25/11" → "25/11/2025" (sin año, usar año actual)
      * "2/7" → "02/07/2025" (sin año y sin ceros, agregar ceros y año actual)
      * "2/7/25" → "02/07/2025" (agregar ceros faltantes)
      * Sin fecha visible → null

    ### 3. CHOFER (chofer)
    - Ubicación: **Arriba a la izquierda** del formulario (debajo de la fecha)
    - Campo: "CHOFER"
    - **IMPORTANTE**: Este campo SIEMPRE estará presente
    - Extrae el nombre completo del chofer como string

    ### 4. GASTOS (gastos)
    - Ubicación: Tabla con título **"GASTOS GENERALES"**
    - Estructura de la tabla:
      * **Columnas**: Cada columna representa una CATEGORÍA de gasto
      * **Filas**: Cada fila representa un PAÍS
    - Cómo extraer:
      * Identifica cada celda con valor numérico
      * El nombre de la columna es la CATEGORÍA
      * El nombre de la fila es el PAÍS
      * El valor es el MONTO
    - **NO incluyas** las filas o columnas de TOTAL

    - **CATEGORÍAS VÁLIDAS** (IMPORTANTE - solo puedes usar estas):
      * PEAJE - para peajes
      * MIGRAC - para migraciones
      * ADUANA - para aduanas
      * TUNEL - para túneles
      * REPRESEN - para representación
      * SENASA - para SENASA
      * ISCAMEN - para ISCAMEN
      * GOMERIA - para gomerías
      * VARIOS - para cualquier otro gasto que no encaje en las categorías anteriores

    - **Mapeo de categorías**: Si encuentras un nombre de columna diferente, debes mapearlo a la categoría válida más cercana:
      * "REPRESENTACIÓN" → REPRESEN
      * "REPRESEN." → REPRESEN
      * Si no hay coincidencia clara → VARIOS

    - Ejemplo: Si en la columna "PEAJE" y fila "CHILE" hay 50000:
      ```json
      {
        "categoria": "PEAJE",
        "monto": 50000,
        "pais": "Chile"
      }
      ```
    - Si una celda está vacía o es 0, NO la incluyas en el listado

    ### 5. VIÁTICOS (viaticos)
    - Ubicación: Tabla con título **"VIATICOS"** (debajo de gastos generales)
    - Busca secciones específicas por país:
      * "VIATICOS EN CHILE" (o CHILE)
      * "VIATICOS EN ARGENTINA" (o ARGENTINA)
      * Pueden existir otras secciones para otros países
    - **Solo extrae el TOTAL** de cada sección de viáticos
    - Pueden darse 3 casos:
      * No hay viáticos en ningún país → lista vacía []
      * Hay viáticos solo en 1 país → lista con 1 elemento
      * Hay viáticos en varios países → lista con varios elementos
    - Ejemplo: Si "VIATICOS EN CHILE" tiene total 30000:
      ```json
      {
        "monto": 30000,
        "pais": "Chile"
      }
      ```

    ## REGLAS IMPORTANTES:

    1. **NO inventes datos**: Si algo no está visible o está vacío, usa null o lista vacía según corresponda
    2. **Precisión numérica**: Extrae los montos exactamente como aparecen (sin símbolos de moneda)
    3. **Nombres de países**: Usa nombres completos y consistentes (Chile, Argentina, Brasil, etc.)
    4. **Categorías**: Usa los nombres de las columnas tal como aparecen en el formulario
    5. **Case sensitivity**: Mantén las mayúsculas/minúsculas de las categorías como aparecen
    6. **Ceros y vacíos**: Si un monto es 0 o la celda está vacía, NO lo incluyas en el listado

    ## FORMATO DE SALIDA:

    Tu respuesta debe ser un JSON con esta estructura exacta:
    ```json
    {
      "numero_op": "string o null",
      "fecha": "dd/MM/yyyy o null si no está visible",
      "chofer": "string (siempre presente)",
      "gastos": [
        {
          "categoria": "string",
          "monto": number,
          "pais": "string"
        }
      ],
      "viaticos": [
        {
          "monto": number,
          "pais": "string"
        }
      ]
    }
    ```
    """
)


def analyze_node(state: GraphState) -> GraphState:
    """Nodo 1: Analiza la imagen y extrae los datos de la rendición"""
    image_url = state["image_url"]
    conductor_desc = state.get("conductor_description")

    system = SystemMessage(content=SYSTEM_PROMPT)

    # Obtener la fecha actual para dar contexto
    from datetime import datetime
    fecha_hoy = datetime.now()
    fecha_hoy_str = fecha_hoy.strftime("%d/%m/%Y")
    anio_actual = fecha_hoy.year

    # Construir el mensaje del usuario
    user_text = f"""Extrae los campos de la rendición de la imagen.

CONTEXTO IMPORTANTE - Fecha actual: {fecha_hoy_str}
Año actual: {anio_actual}

Cuando encuentres fechas sin año completo, usa el año actual ({anio_actual}).
Ejemplos de interpretación:
- "25/11" → 25/11/{anio_actual}
- "2/7" → 02/07/{anio_actual}
- "2/7/25" → 02/07/2025 (el año está especificado)
"""

    # Si hay descripción del conductor, incluirla como contexto adicional
    if conductor_desc:
        user_text += f"\n\nContexto del conductor: \"{conductor_desc}\""

    user = HumanMessage(content=[
        {"type": "text", "text": user_text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ])

    parsed: RendicionSchema = structured_llm.invoke([system, user])
    return {"result": parsed.model_dump()}


def identify_chofer_node(state: GraphState) -> GraphState:
    """Nodo 2: Identifica el chofer correcto desde Supabase usando LLM"""
    result = state["result"]
    chofer_extraido = result.get("chofer")

    if not chofer_extraido:
        # Si no hay chofer, retornar sin cambios
        return state

    # Obtener todos los choferes de Supabase
    response = supabase.table("drivers_info").select("nombre_completo, user_id").execute()
    drivers = response.data

    if not drivers:
        # Si no hay choferes en la BD, retornar sin cambios
        return state

    # Crear prompt para que el LLM identifique el chofer correcto
    drivers_text = "\n".join([f"- {d['nombre_completo']} (ID: {d['user_id']})" for d in drivers])

    chofer_system_prompt = f"""
    Eres un asistente que identifica choferes a partir de nombres escritos a mano.

    Se extrajo el nombre "{chofer_extraido}" de una rendición escrita a mano.

    A continuación está el listado completo de choferes en la base de datos:
    {drivers_text}

    Tu tarea es identificar cuál chofer de la lista corresponde al nombre extraído.

    Considera:
    - Puede haber errores de OCR o escritura manual
    - Los nombres pueden estar en diferente orden (nombre apellido vs apellido nombre)
    - Puede faltar el nombre o apellido completo
    - Busca la mejor coincidencia posible

    Devuelve el chofer que mejor coincida con el nombre extraído.
    """

    system = SystemMessage(content=chofer_system_prompt)
    user = HumanMessage(content=f"Identifica el chofer correcto para: {chofer_extraido}")

    try:
        matched: ChoferMatchSchema = chofer_match_llm.invoke([system, user])

        # Actualizar el resultado con la información del chofer
        result["chofer_info"] = matched.chofer.model_dump()

        return {"result": result}
    except Exception as e:
        # Si hay error en la identificación, retornar sin chofer_info
        print(f"Error identificando chofer: {e}")
        return state


# ---------- Construcción del grafo ----------
graph = StateGraph(GraphState)
graph.add_node("analyze", analyze_node)
graph.add_node("identify_chofer", identify_chofer_node)
graph.set_entry_point("analyze")
graph.add_edge("analyze", "identify_chofer")
graph.add_edge("identify_chofer", END)

app = graph.compile()

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Uso: python app_rendicion.py <IMAGE_URL>")
        sys.exit(1)

    image_url = sys.argv[1]
    out = app.invoke({"image_url": image_url})
    print(json.dumps(out["result"], ensure_ascii=False, indent=2))
