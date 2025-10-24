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
    descripcion: Optional[str] = Field(None, description="En caso de que esté disponible, agregar una descripción del recibo. Ejemplo: 'Compra de combustible en estación Shell'"),
    identificador_fiscal: Optional[str] = Field(None, description="Número de identificación fiscal del emisor del recibo si está disponible. Ejemplos:'CUIT arg, RUT chile, CNPJ brasil, RUC peru y RUC paraguay'")

# ---------- Estado del grafo ----------
class GraphState(TypedDict):
    image_url: str     # input
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
    Eres un agente que ayuda a mi empresa a ordenar las gastos de los choferes.
    Entonces lo que harás será recibir imágenes que los choferes les sacan a las boletas y tu trabajo será,
    devolver en texto en un formato JSON especifico que debes seguir para que luego yo pueda guardar
    esta información en una base de datos y tener el registro.
    # Importante:
    - Hay veces que la referencia o el ID del recibo no está, en ese caso pon null, pero si tu crees que hay algun valor que sea unico en la boleta ponlo ya que luego lo puedo matchear con la fecha de la boleta para saber que no está repetido.
    - La razón social del emisor puede no estar, en ese caso pon null.
    - Debes fijarte en el pais de la boleta y dependiendo el pais, la moneda puede cambiar. En caso de que el país sea Chile la moneda es CLP, si es Argentina es ARS, si es Brasil es BRL, si es Perú es PEN y si es Paraguay es PYG.
    - Si no puedes encontrar algun campo, pon null en vez de inventarte algo. Esto es sumamente importante.
    - Para devolver la fecha, tienes que incluir tanto el dia, mes y año pero tambien debes incluir la hora en minutos y segundos si está disponible.
    """
)


def analyze_node(state: GraphState) -> GraphState:
    image_url = state["image_url"]

    system = SystemMessage(content=SYSTEM_PROMPT)

    user = HumanMessage(content=[
        {"type": "text", "text": "Extrae los campos del recibo de la imagen."},
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
