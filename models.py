# models.py
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import time

# -----------------------------------------------------------------
# Tabla de Enlace (Sin cambios)
# -----------------------------------------------------------------
class RutaParada(SQLModel, table=True):
    ruta_id: Optional[int] = Field(
        default=None, foreign_key="ruta.id", primary_key=True
    )
    parada_id: Optional[int] = Field(
        default=None, foreign_key="parada.id", primary_key=True
    )

# -----------------------------------------------------------------
# Modelos Base (Sin cambios)
# -----------------------------------------------------------------

class RutaBase(SQLModel):
    """Modelo base para Ruta, contiene solo los datos."""
    nombre: str = Field(index=True)

class ParadaBase(SQLModel):
    """Modelo base para Parada, contiene solo los datos."""
    nombre: str = Field(index=True)
    lat: float
    lng: float
    ventana_inicio: time = Field(default=time(8, 0))
    ventana_fin: time = Field(default=time(18, 0))
    tiempo_servicio_min: int = Field(default=30) 

# -----------------------------------------------------------------
# Modelos de Tabla (Sin cambios)
# -----------------------------------------------------------------

class Ruta(RutaBase, table=True):
    """Modelo de la TABLA Ruta."""
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relación a Parada (muchos-a-muchos)
    paradas: List["Parada"] = Relationship(back_populates="rutas", link_model=RutaParada)

class Parada(ParadaBase, table=True):
    """Modelo de la TABLA Parada."""
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relación a Ruta (muchos-a-muchos)
    rutas: List[Ruta] = Relationship(back_populates="paradas", link_model=RutaParada)

class Vehiculo(SQLModel, table=True):
    # (Modelo Vehiculo sin cambios)
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True)
    capacidad: int = Field(default=4)
    lat_inicio: float
    lng_inicio: float
    hora_inicio_turno: time = Field(default=time(7, 0))
    hora_fin_turno: time = Field(default=time(19, 0))

# -----------------------------------------------------------------
# Modelos de API (DTOs)
# -----------------------------------------------------------------

# DTO para crear una Ruta
class RutaCreate(RutaBase):
    parada_ids: List[int]

# DTO para leer una Parada
class ParadaRead(ParadaBase):
    id: int
        
# -----------------------------------------------------------------
# ¡¡AQUÍ ESTÁ LA CORRECCIÓN!!
# -----------------------------------------------------------------
class RutaRead(RutaBase): # <-- Debe heredar de RutaBase
    id: int

# DTO para leer Parada con Rutas
class ParadaReadConRutas(ParadaRead):
    rutas: List[RutaRead] = []

# DTO para leer Ruta con Paradas
class RutaReadConParadas(RutaRead):
    paradas: List[ParadaRead] = []

# DTO para actualizar una Parada (el que arreglamos antes)
class ParadaUpdate(SQLModel):
    nombre: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    ventana_inicio: Optional[time] = None
    ventana_fin: Optional[time] = None
    tiempo_servicio_min: Optional[int] = None