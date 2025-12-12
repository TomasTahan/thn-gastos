import os
from typing import TypedDict, Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()

# LangGraph / LangChain
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Structured output con Pydantic
from pydantic import BaseModel, Field
from typing import List

# ---------- Definimos el schema de salida ----------

class GastoItem(BaseModel):
    categoria: str = Field(..., description="Categoría del gasto")
    monto: float = Field(..., description="Monto del gasto")
    pais: str = Field(..., description="País del gasto. Ejemplos: Chile, Argentina, Brasil, Perú, Paraguay")

class ViaticoItem(BaseModel):
    monto: float = Field(..., description="Monto del viático")
    pais: str = Field(..., description="País del viático. Ejemplos: Chile, Argentina, Brasil, Perú, Paraguay")

class RendicionSchema(BaseModel):
    numero_op: Optional[str] = Field(None, description="Número de operación de la rendición. Ubicado arriba a la derecha. Puede estar vacío (null)")
    chofer: str = Field(..., description="Nombre del chofer que realizó la rendición. Ubicado arriba a la izquierda. Siempre presente")
    gastos: List[GastoItem] = Field(default_factory=list, description="Listado de gastos de la rendición extraídos de la tabla GASTOS GENERALES")
    viaticos: List[ViaticoItem] = Field(default_factory=list, description="Listado de viáticos de la rendición extraídos de la tabla VIATICOS")

# ---------- Estado del grafo ----------
class GraphState(TypedDict):
    image_url: str  # input
    conductor_description: Optional[str]  # descripción verbal del conductor
    result: Dict[str, Any]  # output final

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

    ### 2. CHOFER (chofer)
    - Ubicación: **Arriba a la izquierda** del formulario
    - Campo: "CHOFER"
    - **IMPORTANTE**: Este campo SIEMPRE estará presente
    - Extrae el nombre completo del chofer como string

    ### 3. GASTOS (gastos)
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
    - Ejemplo: Si en la columna "COMBUSTIBLE" y fila "CHILE" hay 50000, creas:
      ```json
      {
        "categoria": "COMBUSTIBLE",
        "monto": 50000,
        "pais": "Chile"
      }
      ```
    - Si una celda está vacía o es 0, NO la incluyas en el listado

    ### 4. VIÁTICOS (viaticos)
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
    image_url = state["image_url"]
    conductor_desc = state.get("conductor_description")

    system = SystemMessage(content=SYSTEM_PROMPT)

    # Construir el mensaje del usuario
    user_text = "Extrae los campos de la rendición de la imagen."

    # Si hay descripción del conductor, incluirla como contexto adicional
    if conductor_desc:
        user_text += f"\n\nContexto del conductor: \"{conductor_desc}\""

    user = HumanMessage(content=[
        {"type": "text", "text": user_text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ])

    parsed: RendicionSchema = structured_llm.invoke([system, user])
    return {"result": parsed.model_dump()}


# ---------- Construcción del grafo ----------
graph = StateGraph(GraphState)
graph.add_node("analyze", analyze_node)
graph.set_entry_point("analyze")
graph.add_edge("analyze", END)

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
