# config.py
import os
from dotenv import load_dotenv

# Esto carga las variables del archivo .env
load_dotenv()

# Ahora, getenv() buscará la variable que acabamos de cargar
MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN")

# Verificación de seguridad
if not MAPBOX_ACCESS_TOKEN:
    print("¡ERROR! MAPBOX_ACCESS_TOKEN no encontrado en el archivo .env")
    # En un sistema real, aquí detendríamos la aplicación