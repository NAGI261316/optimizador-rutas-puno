# database.py
from sqlmodel import SQLModel, create_engine, Session

# 1. Define el nombre de tu archivo de base de datos
DATABASE_FILE = "product.db"
sqlite_url = f"sqlite:///{DATABASE_FILE}"

# 2. Crea el "motor" de la base de datos.
engine = create_engine(sqlite_url, echo=True, 
                       connect_args={"check_same_thread": False})

def create_db_and_tables():
    """
    Función para inicializar la base de datos y crear las tablas.
    """
    SQLModel.metadata.create_all(engine)

# ---------------------------------------------------------
# NUEVA SECCIÓN: Función para obtener una sesión de BD
# ---------------------------------------------------------
def get_session():
    """
    Generador de dependencia que proporciona una sesión de base de datos
    a los endpoints de la API.
    """
    with Session(engine) as session:
        yield session