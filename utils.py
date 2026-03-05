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


SDZ_TYPE_TO_TAGS = {
  "university": {
    "amenity": "university",
  },
  "hospital": {
    "amenity": "hospital",
    "healthcare": "hospital"
  }
}


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


make_feature_tree = lambda facilities: cKDTree(np.array([[geom.centroid.x, geom.centroid.y] for geom in facilities.geometry]) if not facilities.empty else np.empty((0, 2)))
flip_coordinates = lambda polygon: transform(lambda x, y: (y, x), polygon)
transformer_to_meters = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def meters_to_degrees(distance, lat):
  meters_per_degree_lon = METERS_PER_DEGREE_LAT * np.cos(np.radians(lat))
  return distance / ((METERS_PER_DEGREE_LAT + meters_per_degree_lon) / 2)