import h3
import folium
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from scipy.spatial import cKDTree
from IPython.display import display
from geopy.distance import geodesic
from shapely.geometry import Point, Polygon, MultiPolygon, shape
from shapely.strtree import STRtree
from shapely.ops import transform, nearest_points
from shapely import wkt
from pyproj import Transformer
import geopandas as gpd
from tqdm import tqdm
import numpy as np
import pandas as pd
import math
import json
import warnings


def building_dimensions(osmid):
  """
  Params
    - osmid: Element ID in OSM.

  Returns:
    Tuple with height in meters and area in square meters.
    Replaces each field with NaN if the information is not available in OSM.
  """
  try:
    building = BUILDINGS[BUILDINGS["id"] == osmid].iloc[0]
  except:
    return float("nan"), float("nan")

  # check "height" and "building:levels" tags
  try:
    height = float(str(building["height"]).replace("m", ""))
  except:
    try:
      METERS_PER_LEVEL = 3.0
      height = float(building["building:levels"]) * METERS_PER_LEVEL
    except:
      height = float("nan")

  # convert to a meter-based CRS to compute area
  try:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    area = transform(transformer.transform, building.geometry).area
  except:
    area = float("nan")

  return height, area


def building_closest_intersection(buildings_dict):
  """
  Compute the closest street intersection for each address.

  Params:
    - buildings_dict: Dictionary mapping building OSM ID to building features dict.

  Returns: Adds three fields for each building in `buildings_dict`.
    - intersection_osmid: OSM ID of closest intersection
    - intersection_deg: Degree of closest intersection
    - dist_to_intersection: Distance to closest intersection in meters
  """

  if len(STREET_INTERSECTIONS) == 0:
    return {}

  # extract intersection information
  intersection_osmids = STREET_INTERSECTIONS["osmid"].values
  intersection_lats = STREET_INTERSECTIONS["y"].values
  intersection_lons = STREET_INTERSECTIONS["x"].values
  intersection_degs = STREET_INTERSECTIONS["street_count"].values

  # convert intersection coordinates to meters and use KD-Tree for nearest neighbor search
  transformer_to_meters = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
  intersection_x, intersection_y = transformer_to_meters.transform(intersection_lons, intersection_lats)
  tree = cKDTree(np.column_stack([intersection_x, intersection_y]))

  for building_features in buildings_dict.values():
    centroid = building_features["geometry"].centroid
    centroid_x, centroid_y = transformer_to_meters.transform(centroid.x, centroid.y)
    dist, idx = tree.query([centroid_x, centroid_y])

    building_features["intersection_osmid"] = int(intersection_osmids[idx])
    building_features["intersection_deg"] = int(intersection_degs[idx])
    building_features["dist_to_intersection"] = float(dist)


def building_closest_edge(buildings_dict):
  """
  Compute the closest street edge for each building.

  Params:
    - buildings_dict: Dictionary mapping building OSM ID to building features dict.

  Returns: Adds three fields for each building in `buildings_dict`.
    - edge_id: <u>, <v>, <key> tuple of closest street edge.
    - edge_highway_type: Highway type of closest edge.
    - edge_importance: Betweenness centrality of closest edge.
    - dist_to_edge: Distance to closest street edge in meters.
  """
  transformer_to_meters = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

  for building_osmid, building_features in buildings_dict.items():
    centroid = building_features["geometry"].centroid
    centroid_proj = transform(transformer_to_meters.transform, centroid)

    # query nearby edges using spatial index
    nearby_indices = STREET_EDGES_TREE.query(centroid.buffer(0.01))  # ~1 km buffer in degrees
    if not len(nearby_indices):
      nearby_indices = range(len(STREET_EDGES))

    # find closest edge by distance
    min_dist = float("inf")
    edge_idx = None

    for idx in nearby_indices:
      edge_geom = STREET_EDGES.geometry.iloc[idx]
      edge_proj = transform(transformer_to_meters.transform, edge_geom)

      dist = centroid_proj.distance(edge_proj)
      if dist < min_dist:
        min_dist = dist
        edge_idx = idx

    if edge_idx is not None:
      closest_edge = STREET_EDGES.iloc[edge_idx]

      if hasattr(closest_edge, "name") and isinstance(closest_edge.name, tuple):
        edge_id = tuple(int(x) for x in closest_edge.name[:3])
      else:
        u = closest_edge.get("u", 0)
        v = closest_edge.get("v", 0)
        key = closest_edge.get("key", 0)
        # if u, v, key are lists
        edge_id = (
            int(u[0] if isinstance(u, list) else u),
            int(v[0] if isinstance(v, list) else v),
            int(key[0] if isinstance(key, list) else key)
        )
      building_features["edge_id"] = edge_id

      highway = closest_edge.get("highway", float("nan"))
      if isinstance(highway, list):
        building_features["edge_highway_type"] = highway[0] if highway else float("nan")
      else:
        building_features["edge_highway_type"] = highway

      building_features["edge_importance"] = closest_edge.get("importance", float("nan"))
      building_features["dist_to_edge"] = float(min_dist)


def building_nearby_facilities(buildings_dict, poi_thresholds, parking_threshold):
    """
    Compute the number of points of interest -- parks, museums, and campuses -- within given distance thresholds from each building.
    Indicate if there exists a loading dock or parking amenity within a given distance threshold.

    Params:
      - buildings_dict: Dictionary mapping building OSM ID to building features dict.
      - poi_thresholds: List of distance thresholds in meters.
      - parking_threshold: Distance threshold in meters.

    Returns: Adds new fields for each building in `buildings_dict`.
      - nearby_poi_<threshold>: PoI count for each threshold in `poi_thresholds` for each building in `buildings_dict`.
      - loading_dock: Boolean indicating whether a building has a loading dock.
      - parking_amenity: Boolean indicating whether a building has a parking amenity.
    """
    for building_features in buildings_dict.values():
      centroid = building_features["geometry"].centroid
      lon, lat = (centroid.x, centroid.y)

      for threshold in poi_thresholds:
        degree_threshold = meters_to_degrees(threshold, lat)
        indices = POIS_TREE.query_ball_point((lon, lat), degree_threshold)
        building_features[f"nearby_poi_{threshold}"] = len(indices)

      degree_threshold = meters_to_degrees(parking_threshold, lat)
      for key, tree in {
        "loading_dock": SDZ_LOADING_DOCKS_TREE,
        "parking_amenity": SDZ_PARKING_AMENITIES_TREE
      }.items():
        indices = tree.query_ball_point((lon, lat), degree_threshold)
        building_features[key] = len(indices) > 0