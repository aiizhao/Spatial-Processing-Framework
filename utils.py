import osmnx as ox
from scipy.spatial import cKDTree
from shapely.ops import transform
import numpy as np


def sdz_search(place, place_polygon, tags):
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

    output["sdz_of_type"] = sdz_search(place, place_polygon, SDZ_TYPE_TO_TAGS[sdz_type])

    return output


make_feature_tree = lambda facilities: cKDTree(np.array([[geom.centroid.x, geom.centroid.y] for geom in facilities.geometry]) if not facilities.empty else np.empty((0, 2)))
flip_coordinates = lambda polygon: transform(lambda x, y: (y, x), polygon)


def meters_to_degrees(distance, lat):
  meters_per_degree_lat = 111320
  meters_per_degree_lon = meters_per_degree_lat * np.cos(np.radians(lat))
  return distance / ((meters_per_degree_lat + meters_per_degree_lon) / 2)