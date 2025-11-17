# main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import time, timedelta
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import create_db_and_tables, get_session
# Importamos los modelos, incluyendo User y Token
from models import (
    Parada, ParadaUpdate, ParadaRead,
    Ruta, RutaCreate, RutaRead, RutaReadConParadas,
    User, UserCreate, UserRead, Token
)
from sqlmodel import Session, select
from pydantic import BaseModel 

# Importamos la lógica de seguridad y el solver
from auth import (
    get_password_hash, verify_password, create_access_token, 
    ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
)
from jose import JWTError, jwt
from solver import solve_vrp, NoSolutionError

# --- Configuración de Seguridad ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("El servidor está iniciando...")
    create_db_and_tables()
    print("Base de datos y tablas creadas.")
    yield
    print("El servidor se está apagando...")

app = FastAPI(
    title="Sistema de Logística SaaS v3.0",
    description="API Multi-usuario con Login y Seguridad.",
    lifespan=lifespan
)

# --- Configurar CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# DEPENDENCIA DE SEGURIDAD: Obtener Usuario Actual
# ---------------------------------------------------------
async def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # Buscar el usuario en la BD
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception
    return user

# ---------------------------------------------------------
# ENDPOINTS DE AUTENTICACIÓN (Públicos)
# ---------------------------------------------------------

@app.post("/register", response_model=UserRead)
def register_user(*, session: Session = Depends(get_session), user_in: UserCreate):
    """Crea un nuevo usuario en el sistema."""
    # Verificar si el email ya existe
    statement = select(User).where(User.email == user_in.email)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    # Crear usuario con contraseña encriptada
    hashed_pwd = get_password_hash(user_in.password)
    user = User(
        email=user_in.email, 
        password_hash=hashed_pwd,
        nombre_completo=user_in.nombre_completo
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@app.post("/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    """Inicia sesión y devuelve un token JWT."""
    # Buscar usuario (OAuth2 usa 'username' para el campo principal, aquí es el email)
    statement = select(User).where(User.email == form_data.username)
    user = session.exec(statement).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Crear token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Servir Frontend ---
@app.get("/", response_class=FileResponse)
async def read_index():
    return "index.html"

# ---------------------------------------------------------
# ENDPOINTS PROTEGIDOS (Requieren Login)
# ---------------------------------------------------------

# --- PARADAS ---

@app.post("/paradas/", response_model=Parada)
def create_parada(
    *, 
    session: Session = Depends(get_session), 
    parada: Parada,
    current_user: User = Depends(get_current_user) # <-- PROTECCIÓN
):
    # Asignar la parada al usuario actual
    parada.user_id = current_user.id
    
    # Convertir horas
    if isinstance(parada.ventana_inicio, str):
        parada.ventana_inicio = time.fromisoformat(parada.ventana_inicio)
    if isinstance(parada.ventana_fin, str):
        parada.ventana_fin = time.fromisoformat(parada.ventana_fin)
        
    session.add(parada)
    session.commit()
    session.refresh(parada)
    return parada

@app.get("/paradas/", response_model=List[Parada])
def read_paradas(
    *, 
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user) # <-- PROTECCIÓN
):
    # ¡MAGIA! Solo devolvemos las paradas de ESTE usuario
    statement = select(Parada).where(Parada.user_id == current_user.id)
    paradas = session.exec(statement).all()
    return paradas

@app.patch("/paradas/{parada_id}", response_model=Parada)
def update_parada(
    *,
    session: Session = Depends(get_session),
    parada_id: int,
    parada_update: ParadaUpdate,
    current_user: User = Depends(get_current_user)
):
    # Buscar parada Y verificar que sea del usuario
    db_parada = session.get(Parada, parada_id)
    if not db_parada or db_parada.user_id != current_user.id:
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
    parada_id: int,
    current_user: User = Depends(get_current_user)
):
    parada = session.get(Parada, parada_id)
    if not parada or parada.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Parada no encontrada")
    session.delete(parada)
    session.commit()
    return {"ok": True, "detail": "Parada borrada"}

# --- RUTAS ---

@app.post("/rutas/", response_model=RutaReadConParadas)
def create_ruta(
    *,
    session: Session = Depends(get_session),
    ruta_in: RutaCreate,
    current_user: User = Depends(get_current_user)
):
    # Verificar que las paradas pertenezcan al usuario
    statement = select(Parada).where(
        Parada.id.in_(ruta_in.parada_ids),
        Parada.user_id == current_user.id
    )
    paradas = session.exec(statement).all()
    
    if len(paradas) != len(ruta_in.parada_ids):
        raise HTTPException(status_code=404, detail="Una o más paradas no válidas")
        
    db_ruta = Ruta(nombre=ruta_in.nombre, paradas=paradas, user_id=current_user.id)
    session.add(db_ruta)
    session.commit()
    session.refresh(db_ruta)
    
    # Recargar para mostrar
    ruta_guardada = session.get(Ruta, db_ruta.id)
    return ruta_guardada

@app.get("/rutas/", response_model=List[RutaReadConParadas])
def read_rutas(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Solo rutas del usuario
    statement = select(Ruta).where(Ruta.user_id == current_user.id)
    rutas = session.exec(statement).all()
    return rutas

# --- OPTIMIZACIÓN ---

class OptimizeRequest(BaseModel):
    start_lat: float
    start_lng: float
    parada_ids: List[int]

class RouteStop(BaseModel):
    parada: ParadaRead
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
    request: OptimizeRequest,
    current_user: User = Depends(get_current_user) # También protegido
):
    parada_inicio = Parada(
        id=0, nombre="Inicio (Usuario)",
        lat=request.start_lat, lng=request.start_lng,
        ventana_inicio=time(0, 1), ventana_fin=time(23, 59), tiempo_servicio_min=0
    )
    
    # Solo optimizar paradas que pertenezcan al usuario
    statement = select(Parada).where(
        Parada.id.in_(request.parada_ids),
        Parada.user_id == current_user.id
    )
    paradas_destino = session.exec(statement).all()
    
    if len(paradas_destino) != len(request.parada_ids):
        raise HTTPException(status_code=404, detail="Una o más paradas no encontradas o no te pertenecen")

    paradas_totales = [parada_inicio] + paradas_destino
    
    try:
        ruta_data = solve_vrp(paradas_totales) 
        stops_dto = []
        for stop in ruta_data["stops"]:
            stops_dto.append(RouteStop(
                parada=ParadaRead.model_validate(stop["parada"]),
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
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {e}")