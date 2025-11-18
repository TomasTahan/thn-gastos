import os
from typing import TypedDict, Dict, Any, List, Optional

from dotenv import load_dotenv
load_dotenv()

# LangGraph / LangChain
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# Structured output con Pydantic (LangChain lo respeta y parsea)
from pydantic import BaseModel, Field

# ---------- Definimos el schema de salida ----------

class ReceiptSchema(BaseModel):
    referencia: Optional[str] = Field(None, description="Identificador único del recibo si está disponible")
    razon_social: Optional[str] = Field(None, description="Razón social del emisor si está disponible")
    date: str = Field(..., description="Fecha del recibo en formato dd/MM/yyyy y en caso de que esté disponible agregar hora en formato HH:mm:ss")
    total: float = Field(..., description="Monto total del recibo")
    moneda: Optional[str] = Field(None, description="Segun el país de la boleta, la moneda puede cambiar. CLP para Chile, ARS para Argentina, BRL para Brasil, PEN para Perú y PYG para Paraguay.")
    descripcion: Optional[str] = Field(None, description="En caso de que esté disponible, agregar una descripción del recibo. Ejemplo: 'Compra de combustible en estación Shell'")
    identificador_fiscal: Optional[str] = Field(None, description="Número de identificación fiscal del emisor del recibo si está disponible. Ejemplos:'CUIT arg, RUT chile, CNPJ brasil, RUC peru y RUC paraguay'")

    # NUEVO CAMPO
    keywords: List[str] = Field(
        default_factory=list,
        description=(
            "Lista de palabras clave que identifican el tipo de gasto. "
            "Basándote en la imagen Y en la descripción del conductor (si está disponible), "
            "genera 3-5 keywords relevantes que ayuden a categorizar este gasto. "
            "Ejemplos: "
            "- Peaje → ['peaje', 'tag', 'autopista', 'ruta'] "
            "- Combustible → ['combustible', 'diesel', 'gasolina', 'fuel'] "
            "- Hotel → ['hotel', 'alojamiento', 'hospedaje', 'lodging'] "
            "- Comida → ['comida', 'restaurant', 'almuerzo', 'food'] "
            "- Reparación → ['reparacion', 'taller', 'mecanico', 'service'] "
            "Incluye tanto palabras en español como posibles términos en inglés si son relevantes."
        )
    )
# ---------- Estado del grafo ----------
class GraphState(TypedDict):
    image_url: str  # input
    conductor_description: Optional[str]  # NUEVO: descripción verbal del conductor
    result: Dict[str, Any]  # output final

# ---------- Modelo LLM (visión + structured output) ----------
# Usa un modelo con soporte multimodal (p. ej., 'gpt-4o').
# Si tienes otro más nuevo, cambia aquí el nombre.
MODEL_NAME = os.getenv("MODEL_NAME", "google/gemini-2.5-flash-lite-preview-09-2025")

llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model=MODEL_NAME,
    temperature=0,
)

# Empaquetamos el LLM para que DEVUELVA ReceiptSchema (validado).
# LangChain ofrece with_structured_output(...) para enlazar el schema y parsear.
structured_llm = llm.with_structured_output(ReceiptSchema)  # :contentReference[oaicite:2]{index=2}

# ---------- Nodo: analizar imagen ----------
SYSTEM_PROMPT = (
    """
    Eres un agente que ayuda a mi empresa a ordenar los gastos de los choferes.

    Tu trabajo es analizar imágenes de boletas/recibos que los choferes sacan con sus teléfonos
    y extraer información estructurada en formato JSON para guardar en la base de datos.

    ## Campos a extraer:

    1. **referencia**: Identificador único del recibo. Si no hay uno obvio pero ves algún valor único
       (número de factura, código, etc.), úsalo. Si no hay nada, pon null.

    2. **razon_social**: Nombre de la empresa/comercio emisor. Si no está visible, pon null.

    3. **date**: Fecha en formato dd/MM/yyyy. Si hay hora disponible, agrégala en formato HH:mm:ss.
       Ejemplo: "17/11/2025 14:30:00"

    4. **total**: Monto total del recibo como número decimal.

    5. **moneda**: Identifica el país de la boleta:
       - Chile → CLP
       - Argentina → ARS
       - Brasil → BRL
       - Perú → PEN
       - Paraguay → PYG

    6. **descripcion**: Descripción del gasto extraída de la boleta.
       Ejemplo: "Compra de combustible en estación Shell"

    7. **identificador_fiscal**: Número de identificación fiscal del emisor (CUIT, RUT, CNPJ, RUC).
       Si no está, pon null.

    8. **keywords**: IMPORTANTE - Genera 3-5 palabras clave que ayuden a categorizar este gasto.
       - Analiza la imagen para identificar el tipo de gasto
       - Si el conductor proporcionó una descripción verbal, úsala para generar keywords más precisas
       - Incluye términos en español y posibles variantes
       - Ejemplos:
         * "Peaje de Cristo Redentor" → ["peaje", "tag", "autopista", "internacional", "ruta"]
         * "Nafta YPF" → ["combustible", "gasolina", "nafta", "ypf", "fuel"]
         * "Hotel en Santiago" → ["hotel", "alojamiento", "hospedaje", "lodging"]
         * "Almuerzo" → ["comida", "restaurant", "almuerzo", "food", "meal"]
         * "Cambio de aceite" → ["mantenimiento", "reparacion", "taller", "aceite", "service"]

    ## Reglas importantes:
    - NO inventes datos. Si no encuentras algo, usa null.
    - Las keywords son CRÍTICAS para la categorización automática.
    - Usa la descripción del conductor (si está disponible) para hacer keywords más precisas.
    - Sé consistente con las keywords: siempre en minúsculas, sin acentos en lo posible.
    """
)


def analyze_node(state: GraphState) -> GraphState:
    image_url = state["image_url"]
    conductor_desc = state.get("conductor_description")

    system = SystemMessage(content=SYSTEM_PROMPT)

    # Construir el mensaje del usuario
    user_text = "Extrae los campos del recibo de la imagen."

    # Si hay descripción del conductor, incluirla
    if conductor_desc:
        user_text += f"\n\nDescripción del conductor: \"{conductor_desc}\""
        user_text += "\n\nUsa esta descripción para generar keywords más precisas y contextuales."

    user = HumanMessage(content=[
        {"type": "text", "text": user_text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ])

    parsed: ReceiptSchema = structured_llm.invoke([system, user])
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
        print("Uso: python app.py <IMAGE_URL>")
        sys.exit(1)

    image_url = sys.argv[1]
    out = app.invoke({"image_url": image_url})
    print(json.dumps(out["result"], ensure_ascii=False, indent=2))
