import osmnx as ox
import numpy as np
from scipy.spatial import cKDTree
from shapely.ops import transform
from pyproj import Transformer
from constants import *


def sdz_search(place, tags):
  sdzs_in_place = ox.features.features_from_place(place, tags=tags)
  geojsons = sdzs_in_place.to_geo_dict()["features"]
  for geojson in geojsons:
      del geojson["id"]
      geojson["properties"] = { "name": geojson["properties"]["name"] }
  return geojsons


def place_search(place, sdz_type):
    try:
        place_gdf = ox.geocode_to_gdf(place)
        place_polygon = place_gdf.loc[0, "geometry"]
    except Exception as e:
        print("An unexpected error occurred:", e)

    output = {
        "place": place,
        "place_boundary": place_polygon,
    }
    output["sdz_of_type"] = sdz_search(place, SDZ_TYPE_TO_TAGS[sdz_type])
    return output


def meters_to_degrees(distance, lat):
  meters_per_degree_lon = METERS_PER_DEGREE_LAT * np.cos(np.radians(lat))
  return distance / ((METERS_PER_DEGREE_LAT + meters_per_degree_lon) / 2)


transformer_to_meters = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


make_feature_tree = lambda facilities: cKDTree(np.array([[geom.centroid.x, geom.centroid.y] for geom in facilities.geometry]) if not facilities.empty else np.empty((0, 2)))


flip_coordinates = lambda polygon: transform(lambda x, y: (y, x), polygon)


building_hours_prompt = lambda delivery_location_name, delivery_location_address: f'''
You are an expert data extraction system. Your goal is to assist delivery drivers. For the following list of specific delivery locations, your task is to meticulously analyze relevant information online to [1] identify the building opening hours and [2] identify an ideal delivery time window for each day of the week. For example, some buildings may have front desks that only accept package deliveries at certain hours.
Location: {delivery_location_name}
Address: {delivery_location_address}
Constraints: Express all time intervals as either military times in the form "##:##-##:##" or one of ["24/7", "closed", "unknown"]. Only extract information relevant to the physical address. Ignore general company policies, nationwide shipping costs, and return information. You may use the internet and your knowledge to extract information.
Expected output JSON schema, to be used in routing and planning systems:
{{
  "opening_hours": {{
    "mon": "",
    "tue": "",
    "wed": "",
    "thu": "",
    "fri": "",
    "sat": "",
    "sun": ""
  }},
  "delivery_window": {{
    "mon": "",
    "tue": "",
    "wed": "",
    "thu": "",
    "fri": "",
    "sat": "",
    "sun": ""
  }}
}}
Do not return any additional text.
'''
