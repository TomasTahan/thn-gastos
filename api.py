from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Dict, Any
import uvicorn

# Importamos el agente compilado desde app.py
from app import app as langgraph_app

# Creamos la aplicación FastAPI
api = FastAPI(
    title="Receipt Analyzer API",
    description="API para analizar recibos a partir de URLs de imágenes",
    version="1.0.0"
)

# Modelo para la request
class ReceiptRequest(BaseModel):
    image_url: str

# Modelo para la response (opcional, para documentación)
class ReceiptResponse(BaseModel):
    referencia: str | None
    razon_social: str | None
    date: str
    total: float
    moneda: str | None
    descripcion: str | None
    identificador_fiscal: str | None

@api.post("/analyze-receipt", response_model=ReceiptResponse)
async def analyze_receipt(request: ReceiptRequest) -> Dict[str, Any]:
    """
    Analiza una imagen de recibo y extrae la información estructurada.

    Args:
        request: Objeto con la URL de la imagen a analizar

    Returns:
        Diccionario con los campos extraídos del recibo
    """
    try:
        # Invocamos el agente de LangGraph
        result = langgraph_app.invoke({"image_url": request.image_url})
        return result["result"]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la imagen: {str(e)}"
        )

@api.get("/health")
async def health_check():
    """Endpoint para verificar que el servicio está activo"""
    return {"status": "ok", "message": "Receipt Analyzer API is running"}

if __name__ == "__main__":
    # Ejecutar el servidor en localhost:8000
    uvicorn.run(api, host="0.0.0.0", port=8000)
