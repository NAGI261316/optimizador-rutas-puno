# main.py
from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import time
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import create_db_and_tables, get_session
# ¡¡NUEVAS IMPORTACIONES DE MODELS.PY!!
from models import (
    Parada, ParadaUpdate, 
    Ruta, RutaCreate, RutaRead, RutaReadConParadas,
    ParadaRead # Necesario para RutaReadConParadas
)
from sqlmodel import Session, select
from pydantic import BaseModel 

from solver import solve_vrp, NoSolutionError

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("El servidor está iniciando...")
    create_db_and_tables()
    print("Base de datos y tablas creadas.")
    yield
    print("El servidor se está apagando...")

app = FastAPI(
    title="Sistema de Logística Adaptativo Puno v2.0",
    description="API para la optimización de rutas con restricciones reales.",
    lifespan=lifespan
)

# --- Configurar CORS ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Servir el Frontend ---
@app.get("/", response_class=FileResponse)
async def read_index():
    return "index.html"

# ---------------------------------------------------------
# --- Endpoints de Paradas (CRUD) ---
# (Sin cambios)
# ---------------------------------------------------------

@app.post("/paradas/", response_model=Parada)
def create_parada(*, session: Session = Depends(get_session), parada: Parada):
    if isinstance(parada.ventana_inicio, str):
        parada.ventana_inicio = time.fromisoformat(parada.ventana_inicio)
    if isinstance(parada.ventana_fin, str):
        parada.ventana_fin = time.fromisoformat(parada.ventana_fin)
    session.add(parada)
    session.commit()
    session.refresh(parada)
    return parada

@app.get("/paradas/", response_model=List[Parada])
def read_paradas(*, session: Session = Depends(get_session)):
    statement = select(Parada)
    paradas = session.exec(statement).all()
    return paradas

@app.patch("/paradas/{parada_id}", response_model=Parada)
def update_parada(
    *,
    session: Session = Depends(get_session),
    parada_id: int,
    parada_update: ParadaUpdate
):
    db_parada = session.get(Parada, parada_id)
    if not db_parada:
        raise HTTPException(status_code=404, detail="Parada no encontrada")
    update_data = parada_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_parada, key, value)
    session.add(db_parada)
    session.commit()
    session.refresh(db_parada)
    return db_parada

@app.delete("/paradas/{parada_id}")
def delete_parada(
    *,
    session: Session = Depends(get_session),
    parada_id: int
):
    parada = session.get(Parada, parada_id)
    if not parada:
        raise HTTPException(status_code=404, detail="Parada no encontrada")
    session.delete(parada)
    session.commit()
    return {"ok": True, "detail": f"Parada '{parada.nombre}' borrada."}

# ---------------------------------------------------------
# ¡¡NUEVA SECCIÓN: Endpoints de Rutas (Guardar/Cargar)!!
# ---------------------------------------------------------

@app.post("/rutas/", response_model=RutaReadConParadas)
def create_ruta(
    *,
    session: Session = Depends(get_session),
    ruta_in: RutaCreate
):
    """
    Crea (guarda) una nueva ruta con una lista de paradas.
    """
    print(f"Creando ruta: {ruta_in.nombre}")
    
    # 1. Buscar las paradas en la BD que coincidan con los IDs
    statement = select(Parada).where(Parada.id.in_(ruta_in.parada_ids))
    paradas = session.exec(statement).all()
    
    # 2. Verificar si encontramos todas las paradas
    if len(paradas) != len(ruta_in.parada_ids):
        raise HTTPException(status_code=404, detail="Una o más paradas no se encontraron")
        
    # 3. Crear el objeto Ruta y asignarle las paradas
    # ¡SQLModel se encarga de la tabla de enlace (RutaParada) automáticamente!
    db_ruta = Ruta(nombre=ruta_in.nombre, paradas=paradas)
    
    # 4. Guardar en la BD
    session.add(db_ruta)
    session.commit()
    session.refresh(db_ruta)
    
    # 5. Devolvemos la ruta completa (usando el modelo DTO)
    # Es necesario volver a cargarla para que SQLModel popule bien
    # las relaciones en el modelo de respuesta
    ruta_guardada = session.get(Ruta, db_ruta.id)
    return ruta_guardada

@app.get("/rutas/", response_model=List[RutaReadConParadas])
def read_rutas(
    *,
    session: Session = Depends(get_session)
):
    """
    Lista todas las rutas guardadas y las paradas dentro de cada una.
    """
    print("Obteniendo lista de rutas guardadas")
    statement = select(Ruta)
    rutas = session.exec(statement).all()
    return rutas

# ---------------------------------------------------------
# --- Endpoint de Optimización (API) ---
# (Sin cambios)
# ---------------------------------------------------------

class OptimizeRequest(BaseModel):
    start_lat: float
    start_lng: float
    parada_ids: List[int]

class RouteStop(BaseModel):
    parada: ParadaRead # Devolvemos el DTO de Parada
    arrival_time: str  
    departure_time: str
    travel_time_to_stop: str

class OptimizeResponse(BaseModel):
    stops: List[RouteStop]
    total_duration_seconds: int
    total_duration_str: str

@app.post("/api/v2/optimizar-ruta", response_model=OptimizeResponse)
def optimizar_ruta(
    *,
    session: Session = Depends(get_session),
    request: OptimizeRequest
):
    # Creamos una Parada "virtual" (no la guardamos en BD)
    parada_inicio = Parada(
        id=0, # Le damos un ID temporal
        nombre="Inicio (Usuario)",
        lat=request.start_lat,
        lng=request.start_lng,
        ventana_inicio=time(0, 1),
        ventana_fin=time(23, 59),
        tiempo_servicio_min=0
    )
    
    statement = select(Parada).where(Parada.id.in_(request.parada_ids))
    paradas_destino = session.exec(statement).all()
    
    if len(paradas_destino) != len(request.parada_ids):
        raise HTTPException(status_code=404, detail="Una o más paradas no se encontraron")

    paradas_totales = [parada_inicio] + paradas_destino
    
    try:
        ruta_data = solve_vrp(paradas_totales) 
        
        # Convertimos las paradas del solver a ParadaRead para la respuesta
        stops_dto = []
        for stop in ruta_data["stops"]:
            stops_dto.append(RouteStop(
                parada=ParadaRead.model_validate(stop["parada"]), # Convertir Parada a ParadaRead
                arrival_time=stop["arrival_time"],
                departure_time=stop["departure_time"],
                travel_time_to_stop=stop["travel_time_to_stop"]
            ))

        return OptimizeResponse(
            stops=stops_dto,
            total_duration_seconds=ruta_data["total_duration_seconds"],
            total_duration_str=ruta_data["total_duration_str"]
        )
    
    except NoSolutionError as e:
        print(f"Error 400 (Petición Imposible): {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        print(f"Error 500 (Error Interno): {e}")
        raise HTTPException(status_code=500, detail=f"Ocurrió un error interno en el servidor: {e}")