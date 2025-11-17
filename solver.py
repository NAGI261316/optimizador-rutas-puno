# solver.py
import math
import httpx
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from typing import List, Dict
from datetime import time, timedelta

from models import Parada
from config import MAPBOX_ACCESS_TOKEN

# -----------------------------------------------------------------
# ¡¡ESTA ES LA CLASE QUE FALTABA!!
# -----------------------------------------------------------------
class NoSolutionError(Exception):
    """Error personalizado que se lanza cuando OR-Tools no encuentra solución."""
    pass
# -----------------------------------------------------------------

def get_real_time_matrix(paradas: List[Parada]) -> List[List[int]]:
    """
    *** FUNCIÓN REAL ***
    Llama a la API Matrix de Mapbox...
    """
    print("Llamando a la API Matrix de Mapbox...")
    
    coordinates_str = ";".join([f"{p.lng},{p.lat}" for p in paradas])
    
    url = f"https://api.mapbox.com/directions-matrix/v1/mapbox/driving-traffic/{coordinates_str}"
    url_params = {
        "annotations": "duration",
        "access_token": MAPBOX_ACCESS_TOKEN
    }

    try:
        with httpx.Client() as client:
            response = client.get(url, params=url_params, timeout=20.0)
            response.raise_for_status() 
            data = response.json()
            
            if data['code'] != 'Ok':
                raise Exception(f"Mapbox API no devolvió 'Ok': {data.get('message', '')}")
            
            matrix_float = data['durations']
            matrix_int = [[int(t) for t in row] for row in matrix_float]
            
            print("Matriz de tiempos reales obtenida.")
            return matrix_int
            
    except httpx.HTTPStatusError as e:
        print(f"Error HTTP llamando a Mapbox: {e}")
        raise Exception(f"Error de Mapbox (código {e.response.status_code}): No se pudo obtener la matriz de tiempos.")
    except Exception as e:
        print(f"Error procesando respuesta de Mapbox: {e}")
        raise


def time_to_seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second

# --- Funciones de ayuda para el itinerario ---
def seconds_to_time_str(seconds_from_midnight: int) -> str:
    hours = seconds_from_midnight // 3600
    minutes = (seconds_from_midnight % 3600) // 60
    period = "AM"
    if hours >= 12: period = "PM"
    if hours == 0: hours = 12
    if hours > 12: hours -= 12
    return f"{hours:02d}:{minutes:02d} {period}"

def seconds_to_duration_str(total_seconds: int) -> str:
    if total_seconds < 60: return f"{total_seconds} seg"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours} h {minutes:02d} min"
    else:
        return f"{minutes} min"


def solve_vrp(paradas: List[Parada]):
    """
    Resuelve el Problema de Enrutamiento de Vehículos (VRP) con Ventanas de Tiempo.
    """
    
    print(f"Iniciando solver de OR-Tools para {len(paradas)} paradas.")
    
    # ... (Secciones 1, 2, 3, 4, 5 - igual que antes) ...
    
    # 1. Crear el modelo de datos
    data = {}
    data['time_windows'] = []
    data['service_times'] = []
    
    for p in paradas:
        start_sec = time_to_seconds(p.ventana_inicio)
        end_sec = time_to_seconds(p.ventana_fin)
        data['time_windows'].append((start_sec, end_sec))
        data['service_times'].append(p.tiempo_servicio_min * 60)
        
    data['num_vehicles'] = 1
    data['depot'] = 0

    # 2. Crear la Matriz de Tiempos de Viaje
    try:
        data['time_matrix'] = get_real_time_matrix(paradas)
    except Exception as e:
        raise e

    # 3. Configurar el Solver
    manager = pywrapcp.RoutingIndexManager(
        len(data['time_matrix']), data['num_vehicles'], data['depot']
    )
    routing = pywrapcp.RoutingModel(manager)

    # 4. Definir el "costo" (tiempo)
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['time_matrix'][from_node][to_node] + data['service_times'][from_node]

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 5. Añadir restricción de Ventanas de Tiempo
    time_dim = 'Time'
    routing.AddDimension(
        transit_callback_index, 900, 86400, False, time_dim
    )
    time_dimension = routing.GetDimensionOrDie(time_dim)
    
    for location_idx, time_window in enumerate(data['time_windows']):
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])

    # 6. Configurar búsqueda y resolver
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    print("Resolviendo...")
    solution = routing.SolveWithParameters(search_parameters)

    # -----------------------------------------------------------------
    # SECCIÓN 7 (MODIFICADA PARA LANZAR EL ERROR)
    # -----------------------------------------------------------------
    if not solution:
        print("No se encontró solución.")
        # ¡LANZAMOS NUESTRO ERROR PERSONALIZADO!
        raise NoSolutionError("No se encontró una ruta. Es imposible cumplir con todas las ventanas de tiempo. Intenta con menos paradas o revisa sus horarios.")

    # (El resto del código es igual que antes)
    print("Solución encontrada. Construyendo itinerario...")
    itinerary = []
    index = routing.Start(0)
    time_dimension = routing.GetDimensionOrDie('Time')
    last_departure_time_seconds = 0

    while not routing.IsEnd(index):
        nodo_idx = manager.IndexToNode(index)
        parada = paradas[nodo_idx]
        
        arrival_time_seconds = solution.Value(time_dimension.CumulVar(index))
        service_time_seconds = data['service_times'][nodo_idx]
        departure_time_seconds = arrival_time_seconds + service_time_seconds
        travel_time_seconds = arrival_time_seconds - last_departure_time_seconds
        last_departure_time_seconds = departure_time_seconds

        itinerary.append({
            "parada": parada,
            "arrival_time": seconds_to_time_str(arrival_time_seconds),
            "departure_time": seconds_to_time_str(departure_time_seconds),
            "travel_time_to_stop": seconds_to_duration_str(travel_time_seconds)
        })
        index = solution.Value(routing.NextVar(index))

    total_duration_seconds = solution.Value(time_dimension.CumulVar(index))
    total_duration_seconds -= solution.Value(time_dimension.CumulVar(routing.Start(0)))
    
    return {
        "stops": itinerary,
        "total_duration_seconds": total_duration_seconds,
        "total_duration_str": seconds_to_duration_str(total_duration_seconds)
    }