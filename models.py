# models.py
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import time

# -----------------------------------------------------------------
# NUEVO: Modelo de Usuario
# -----------------------------------------------------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str # Nunca guardamos la password real
    nombre_completo: Optional[str] = None

    # Relaciones (Un usuario tiene muchas rutas y paradas)
    rutas: List["Ruta"] = Relationship(back_populates="owner")
    paradas: List["Parada"] = Relationship(back_populates="owner")


# -----------------------------------------------------------------
# Tabla de Enlace (Sin cambios)
# -----------------------------------------------------------------
class RutaParada(SQLModel, table=True):
    ruta_id: Optional[int] = Field(default=None, foreign_key="ruta.id", primary_key=True)
    parada_id: Optional[int] = Field(default=None, foreign_key="parada.id", primary_key=True)

# -----------------------------------------------------------------
# Modelos Base
# -----------------------------------------------------------------
class RutaBase(SQLModel):
    nombre: str = Field(index=True)

class ParadaBase(SQLModel):
    nombre: str = Field(index=True)
    lat: float
    lng: float
    ventana_inicio: time = Field(default=time(8, 0))
    ventana_fin: time = Field(default=time(18, 0))
    tiempo_servicio_min: int = Field(default=30) 

# -----------------------------------------------------------------
# Modelos de Tabla (CON DUEÑO)
# -----------------------------------------------------------------
class Ruta(RutaBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # ¡NUEVO! Dueño de la ruta
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    owner: Optional[User] = Relationship(back_populates="rutas")

    paradas: List["Parada"] = Relationship(back_populates="rutas", link_model=RutaParada)

class Parada(ParadaBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # ¡NUEVO! Dueño de la parada
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    owner: Optional[User] = Relationship(back_populates="paradas")

    rutas: List[Ruta] = Relationship(back_populates="paradas", link_model=RutaParada)

# -----------------------------------------------------------------
# Modelos de API (DTOs)
# -----------------------------------------------------------------
class RutaCreate(RutaBase):
    parada_ids: List[int]

class ParadaRead(ParadaBase):
    id: int
        
class RutaRead(RutaBase): 
    id: int

class ParadaReadConRutas(ParadaRead):
    rutas: List[RutaRead] = []

class RutaReadConParadas(RutaRead):
    paradas: List[ParadaRead] = []

class ParadaUpdate(SQLModel):
    nombre: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    ventana_inicio: Optional[time] = None
    ventana_fin: Optional[time] = None
    tiempo_servicio_min: Optional[int] = None

# NUEVO: DTOs para Usuario
class UserCreate(SQLModel):
    email: str
    password: str
    nombre_completo: Optional[str] = None

class UserRead(SQLModel):
    id: int
    email: str
    nombre_completo: Optional[str] = None
    
class Token(SQLModel):
    access_token: str
    token_type: str