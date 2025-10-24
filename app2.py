import os
from typing import TypedDict, Dict, Any, List, Optional

from dotenv import load_dotenv
load_dotenv()

# LangGraph / LangChain
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Structured output con Pydantic (LangChain lo respeta y parsea)
from pydantic import BaseModel, Field

# ---------- Definimos el schema de salida ----------
class RemitoCombustibleSchema(BaseModel):
    """Estructura de datos para registrar una carga de combustible."""
    
    numero_remito: str = Field(..., description="Número del remito o comprobante de carga.")
    fecha: str = Field(..., description="Fecha de emisión del remito en formato ISO (YYYY-MM-DD).")
    patente: str = Field(..., description="Patente del camión o camioneta que recibe el combustible.")
    kilometraje: Optional[float] = Field(None, description="Kilometraje registrado al momento de la carga (puede omitirse).")
    litros: float = Field(..., description="Cantidad de litros cargados según el remito.")
    historico_inicial: float = Field(..., description="Valor inicial del histórico de combustible antes de la carga.")
    historico_final: float = Field(..., description="Valor final del histórico de combustible después de la carga.")
    nombre_conductor: str = Field(..., description="Nombre completo del conductor del vehículo.")
    nombre_operario: str = Field(..., description="Nombre completo del operario o despachador que realizó la carga.")

# ---------- Estado del grafo ----------
class GraphState(TypedDict):
    image_url: str     # input
    result: Dict[str, Any]  # output final

# ---------- Modelo LLM (visión + structured output) ----------
# Usa un modelo con soporte multimodal (p. ej., 'gpt-4o').
# Si tienes otro más nuevo, cambia aquí el nombre.
MODEL_NAME = os.getenv("MODEL_NAME", "qwen/qwen3-vl-235b-a22b-thinking")

llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model=MODEL_NAME,
    temperature=0,
)

# Empaquetamos el LLM para que DEVUELVA RemitoCombustibleSchema (validado).
# LangChain ofrece with_structured_output(...) para enlazar el schema y parsear.
structured_llm = llm.with_structured_output(RemitoCombustibleSchema)  # :contentReference[oaicite:2]{index=2}

# ---------- Nodo: analizar imagen ----------
SYSTEM_PROMPT = (
    """
Sos un agente extractor de datos de remitos de combustible. Recibís una o varias imágenes (fotos) de remitos completados por operarios del taller y tu tarea es extraer de cada remito los datos solicitados y devolverlos exclusivamente en formato JSON válido, siguiendo el esquema indicado. Luego, estos datos serán cargados ordenadamente en una planilla de Excel.

Tu objetivo principal es identificar y estructurar la siguiente información de cada remito:

numero_remito: número del remito o comprobante.

fecha: fecha del remito en formato ISO YYYY-MM-DD.

patente: patente del camión o camioneta.

kilometraje: lectura del odómetro al momento de la carga (puede omitirse si no está visible).

litros: cantidad de litros cargados.

historico_inicial: valor inicial del histórico antes de la carga.

historico_final: valor final del histórico después de la carga.

nombre_conductor: nombre del conductor del vehículo.

nombre_operario: nombre del operario o despachador que realizó la carga.

Normas y formato de salida:

Tu salida debe ser únicamente el JSON final, sin texto adicional, sin comentarios y sin formato Markdown.

Si hay varios remitos en una misma imagen, devolvés una lista de objetos JSON.

Si un campo obligatorio (todos excepto kilometraje) no está en el remito, no devuelvas ese remito.

El JSON debe cumplir el siguiente formato:
{
  "numero_remito": "string",
  "fecha": "YYYY-MM-DD",
  "patente": "string",
  "kilometraje": 0.0,
  "litros": 0.0,
  "historico_inicial": 0.0,
  "historico_final": 0.0,
  "nombre_conductor": "string",
  "nombre_operario": "string"
}
Reglas de normalización:

Convertí las fechas a formato ISO YYYY-MM-DD. Si ves 14/10/25, interpretalo como 2025-10-14.

La patente debe estar en mayúsculas, sin espacios, y puede tener formato antiguo (ABC123) o Mercosur (AB123CD). Nunca va a partir con un numero la patente.


Capitalizá los nombres de conductor y operario.

Si no tiene el kilometraje, asigná null.

Aceptá etiquetas comunes del remito como:

“Remito N°”, “Fecha”, “Patente”, “Km”, “Litros”, “Histórico Inicial”, “Histórico Final”, “Conductor”, “Operario”.

Los valores historicos en el remito estan donde esta el signo $

No hagas nada más que esto. Tu única salida debe ser el JSON limpio y validado.
    """
)


def analyze_node(state: GraphState) -> GraphState:
    image_url = state["image_url"]

    system = SystemMessage(content=SYSTEM_PROMPT)

    user = HumanMessage(content=[
        {"type": "text", "text": "Extrae los campos del recibo de la imagen."},
        {"type": "image_url", "image_url": {"url": image_url}},
    ])

    parsed: RemitoCombustibleSchema = structured_llm.invoke([system, user])
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
