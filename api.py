from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Dict, Any, Optional, List
import uvicorn
import logging


# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importamos el agente compilado desde app.py
from app import app as langgraph_app

# Creamos la aplicación FastAPI
api = FastAPI(
    title="Receipt Analyzer API",
    description="API para analizar recibos a partir de URLs de imágenes",
    version="1.0.0"
)

# Configurar CORS
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo para la request
class ReceiptRequest(BaseModel):
    image_url: str
    conductor_description: Optional[str] = None  # NUEVO campo opcional

# Modelo para la response (opcional, para documentación)
class ReceiptResponse(BaseModel):
    referencia: str | None
    razon_social: str | None
    date: str
    total: float
    moneda: str | None
    descripcion: str | None
    identificador_fiscal: str | None
    keywords: List[str]  # NUEVO

@api.post("/analyze-receipt", response_model=ReceiptResponse)
async def analyze_receipt(request: ReceiptRequest) -> Dict[str, Any]:
    """
    Analiza una imagen de recibo y extrae la información estructurada.

    Args:
        request: Objeto con la URL de la imagen y opcionalmente descripción del conductor

    Returns:
        Diccionario con los campos extraídos del recibo incluyendo keywords
    """
    try:
        logger.info(f"Analizando imagen: {request.image_url}")
        if request.conductor_description:
            logger.info(f"Con descripción del conductor: {request.conductor_description}")

        # Invocamos el agente de LangGraph
        result = langgraph_app.invoke({
            "image_url": request.image_url,
            "conductor_description": request.conductor_description
        })

        logger.info(f"Análisis completado. Keywords generadas: {result['result'].get('keywords', [])}")
        return result["result"]

    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
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
