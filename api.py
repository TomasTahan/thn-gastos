from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Dict, Any, Optional
import uvicorn
import logging
from datetime import datetime


# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importamos los agentes compilados
from app import app as langgraph_app
from app_rendicion import app as langgraph_rendicion_app

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
    conductor_description: Optional[str] = None  # Campo opcional

    class Config:
        json_schema_extra = {
            "example": {
                "image_url": "https://ejemplo.com/imagen.jpg"
            }
        }

# Modelo para la response de recibos
class ReceiptResponse(BaseModel):
    referencia: str | None
    razon_social: str | None
    date: str
    total: float
    moneda: str | None
    descripcion: str | None
    identificador_fiscal: str | None

# Modelo para chofer info
class ChoferInfoResponse(BaseModel):
    nombre_completo: str
    user_id: str

# Modelo para la response de rendiciones
class RendicionResponse(BaseModel):
    numero_op: str | None
    fecha: str  # Siempre presente (usa fecha de hoy si no se encuentra en la imagen)
    chofer: str
    gastos: list
    viaticos: list
    chofer_info: ChoferInfoResponse | None = None

@api.post("/analyze-receipt", response_model=ReceiptResponse)
async def analyze_receipt(request: ReceiptRequest) -> Dict[str, Any]:
    """
    Analiza una imagen de recibo y extrae la información estructurada.

    Args:
        request: Objeto con la URL de la imagen y opcionalmente descripción del conductor

    Returns:
        Diccionario con los campos extraídos del recibo
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

        logger.info(f"Análisis completado exitosamente")
        return result["result"]

    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la imagen: {str(e)}"
        )

@api.post("/analyze-rendicion", response_model=RendicionResponse)
async def analyze_rendicion(request: ReceiptRequest) -> Dict[str, Any]:
    """
    Analiza una imagen de rendición y extrae la información estructurada.

    Args:
        request: Objeto con la URL de la imagen y opcionalmente descripción del conductor

    Returns:
        Diccionario con los campos extraídos de la rendición
    """
    try:
        logger.info(f"Analizando imagen de rendición: {request.image_url}")
        if request.conductor_description:
            logger.info(f"Con descripción del conductor: {request.conductor_description}")

        # Invocamos el agente de rendiciones de LangGraph
        result = langgraph_rendicion_app.invoke({
            "image_url": request.image_url,
            "conductor_description": request.conductor_description
        })

        # Si la fecha es null, usar la fecha de hoy
        response_data = result["result"]
        if response_data.get("fecha") is None:
            today = datetime.now().strftime("%d/%m/%Y")
            response_data["fecha"] = today
            logger.info(f"Fecha no encontrada en la imagen, usando fecha de hoy: {today}")

        logger.info(f"Análisis completado exitosamente")
        return response_data

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
