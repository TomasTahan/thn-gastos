# Guía de Despliegue en EasyPanel

Esta guía te ayudará a desplegar la Receipt Analyzer API en un VPS usando EasyPanel.

## Requisitos Previos

1. **VPS con EasyPanel instalado**
   - Asegúrate de tener EasyPanel configurado en tu VPS
   - Acceso SSH al VPS (opcional, pero recomendado)

2. **Repositorio Git**
   - Sube tu código a un repositorio Git (GitHub, GitLab, Bitbucket)
   - O prepárate para subir los archivos manualmente

3. **Variables de Entorno**
   - `OPENROUTER_API_KEY`: Tu API key de OpenRouter
   - `MODEL_NAME`: (Opcional) Nombre del modelo a usar

## Opción 1: Despliegue desde GitHub (Recomendado)

### Paso 1: Preparar el Repositorio

1. Sube tu código a GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Receipt Analyzer API"
   git branch -M main
   git remote add origin <tu-repositorio-git>
   git push -u origin main
   ```

### Paso 2: Configurar en EasyPanel

1. **Accede a EasyPanel**
   - Ve a la URL de tu EasyPanel (ej: `https://tu-dominio.com:3000`)
   - Inicia sesión con tus credenciales

2. **Crear Nuevo Proyecto**
   - Click en "New Project" o "+" para crear un nuevo proyecto
   - Selecciona "GitHub" como fuente

3. **Conectar Repositorio**
   - Autoriza EasyPanel a acceder a tu GitHub
   - Selecciona el repositorio con tu código
   - Selecciona la rama `main`

4. **Configurar el Servicio**
   - **Build Method**: Docker
   - **Dockerfile Path**: `./Dockerfile`
   - **Port**: `8000`
   - **Domain**: Configura tu dominio o usa el subdominio de EasyPanel

5. **Configurar Variables de Entorno**
   - Ve a la sección "Environment Variables"
   - Agrega las siguientes variables:
     ```
     OPENROUTER_API_KEY=tu_api_key_aqui
     MODEL_NAME=google/gemini-2.5-flash-lite-preview-09-2025
     ```

6. **Deploy**
   - Click en "Deploy" para iniciar el despliegue
   - Espera a que se construya la imagen y se inicie el contenedor

### Paso 3: Verificar el Despliegue

1. Una vez completado, accede a:
   - `https://tu-dominio.com/health` - Debería retornar `{"status": "ok", ...}`
   - `https://tu-dominio.com/docs` - Documentación interactiva de la API

## Opción 2: Despliegue Manual con Docker

### Paso 1: Subir Archivos al VPS

1. Conecta por SSH a tu VPS:
   ```bash
   ssh usuario@tu-vps-ip
   ```

2. Crea un directorio para el proyecto:
   ```bash
   mkdir -p ~/receipt-analyzer
   cd ~/receipt-analyzer
   ```

3. Sube los archivos necesarios:
   ```bash
   # Desde tu máquina local
   scp app.py api.py requirements.txt Dockerfile docker-compose.yml .env usuario@tu-vps-ip:~/receipt-analyzer/
   ```

### Paso 2: Configurar Variables de Entorno

1. Edita el archivo `.env`:
   ```bash
   nano .env
   ```

2. Agrega tus credenciales:
   ```
   OPENROUTER_API_KEY=tu_api_key_aqui
   MODEL_NAME=google/gemini-2.5-flash-lite-preview-09-2025
   ```

### Paso 3: Construir y Ejecutar con Docker

1. Construir la imagen:
   ```bash
   docker build -t receipt-analyzer .
   ```

2. Ejecutar el contenedor:
   ```bash
   docker run -d \
     --name receipt-analyzer \
     -p 8000:8000 \
     --env-file .env \
     --restart unless-stopped \
     receipt-analyzer
   ```

   O usando docker-compose:
   ```bash
   docker-compose up -d
   ```

### Paso 4: Configurar Nginx (Opcional)

Si quieres usar un dominio, configura Nginx como proxy reverso:

1. Instala Nginx (si no está instalado):
   ```bash
   sudo apt update
   sudo apt install nginx
   ```

2. Crea un archivo de configuración:
   ```bash
   sudo nano /etc/nginx/sites-available/receipt-analyzer
   ```

3. Agrega la siguiente configuración:
   ```nginx
   server {
       listen 80;
       server_name tu-dominio.com;

       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

4. Activa el sitio:
   ```bash
   sudo ln -s /etc/nginx/sites-available/receipt-analyzer /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

5. (Opcional) Configura SSL con Let's Encrypt:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d tu-dominio.com
   ```

## Opción 3: Despliegue con EasyPanel (Interfaz Web)

### Paso 1: Crear Aplicación desde Docker Image

1. En EasyPanel, ve a "Apps" > "Create App"
2. Selecciona "Docker Image"
3. Configura:
   - **App Name**: `receipt-analyzer`
   - **Image**: Construye la imagen primero o usa un registry
   - **Port**: `8000`

### Paso 2: Configurar desde GitHub con Auto-Deploy

1. En EasyPanel, crea un nuevo servicio
2. Selecciona "GitHub" como fuente
3. Conecta tu repositorio
4. EasyPanel detectará automáticamente el `Dockerfile`
5. Configura las variables de entorno
6. Activa "Auto Deploy" para deploys automáticos en cada push

## Endpoints de la API

Una vez desplegado, tendrás acceso a:

- **POST /analyze-receipt**: Analizar un recibo
  ```json
  {
    "image_url": "https://ejemplo.com/recibo.jpg"
  }
  ```

- **GET /health**: Verificar estado del servicio

- **GET /docs**: Documentación interactiva (Swagger UI)

- **GET /redoc**: Documentación alternativa (ReDoc)

## Probar la API

Puedes probar la API con curl:

```bash
curl -X POST "https://tu-dominio.com/analyze-receipt" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://ejemplo.com/tu-recibo.jpg"
  }'
```

O desde Python:

```python
import requests

url = "https://tu-dominio.com/analyze-receipt"
data = {"image_url": "https://ejemplo.com/tu-recibo.jpg"}

response = requests.post(url, json=data)
print(response.json())
```

## Monitoreo y Logs

### Ver logs en EasyPanel
- Ve a tu aplicación en EasyPanel
- Click en "Logs" para ver los logs en tiempo real

### Ver logs con Docker (despliegue manual)
```bash
docker logs -f receipt-analyzer
```

### Ver logs con docker-compose
```bash
docker-compose logs -f
```

## Troubleshooting

### La API no responde
1. Verifica que el contenedor esté corriendo:
   ```bash
   docker ps
   ```

2. Verifica los logs:
   ```bash
   docker logs receipt-analyzer
   ```

### Error de API Key
- Verifica que la variable `OPENROUTER_API_KEY` esté configurada correctamente
- Comprueba que la API key sea válida

### Error de build
- Asegúrate de que todos los archivos estén en el directorio
- Verifica que el `requirements.txt` esté completo

## Actualizar la Aplicación

### Con EasyPanel + GitHub (Auto-deploy)
- Simplemente haz `git push` y EasyPanel desplegará automáticamente

### Manualmente
```bash
# Detener el contenedor actual
docker-compose down

# Actualizar el código
git pull

# Reconstruir y reiniciar
docker-compose up -d --build
```

## Seguridad

- **No expongas tu `.env` en el repositorio**
- Usa HTTPS en producción (EasyPanel lo configura automáticamente)
- Considera agregar autenticación a la API si es necesario
- Limita el acceso a la API solo a IPs/dominios autorizados si es posible

## Recursos Adicionales

- [Documentación de EasyPanel](https://easypanel.io/docs)
- [Documentación de FastAPI](https://fastapi.tiangolo.com/)
- [Documentación de Docker](https://docs.docker.com/)
