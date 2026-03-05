import numpy as np
from scipy.spatial import cKDTree
from shapely.ops import transform
from pyproj import Transformer
from tqdm import tqdm
from utils import *


class BuildingsData:
    def __init__(self, osm_data):
        self.osm_data = osm_data
        self.buildings_features = dict()

        for _, row in tqdm(self.osm_data.sdz_buildings.iterrows(), total=len(self.osm_data.sdz_buildings)):
            osmid = row["id"]
            height, area = self._building_dimensions(row)

            self.buildings_features[osmid] = {
                "name": row.get("name", float("nan")),
                "height": height,
                "area": area,
                "geometry": row["geometry"],
                "street": row.get("addr:street", float("nan")),
                "city": row.get("addr:city", float("nan")),
                "state": row.get("addr:state", float("nan")),
                "country": row.get("addr:country", float("nan"))
            }

    def _building_dimensions(self, building):
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


    def building_closest_intersection(self):
        """
        Compute the closest street intersection for each address.

        Returns: Adds three fields for each building in `buildings_features`.
            - intersection_osmid: OSM ID of closest intersection
            - intersection_deg: Degree of closest intersection
            - dist_to_intersection: Distance to closest intersection in meters
        """

        if len(self.osm_data.street_intersections) == 0:
            return {}

        # extract intersection information
        intersection_osmids = self.osm_data.street_intersections["osmid"].values
        intersection_lats = self.osm_data.street_intersections["y"].values
        intersection_lons = self.osm_data.street_intersections["x"].values
        intersection_degs = self.osm_data.street_intersections["street_count"].values

        # convert intersection coordinates to meters and use KD-Tree for nearest neighbor search
        transformer_to_meters = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        intersection_x, intersection_y = transformer_to_meters.transform(intersection_lons, intersection_lats)
        tree = cKDTree(np.column_stack([intersection_x, intersection_y]))

        for building_features in self.buildings_features.values():
            centroid = building_features["geometry"].centroid
            centroid_x, centroid_y = transformer_to_meters.transform(centroid.x, centroid.y)
            dist, idx = tree.query([centroid_x, centroid_y])

            building_features["intersection_osmid"] = int(intersection_osmids[idx])
            building_features["intersection_deg"] = int(intersection_degs[idx])
            building_features["dist_to_intersection"] = float(dist)


    def building_closest_edge(self):
        """
        Compute the closest street edge for each building.

        Adds three fields for each building in `buildings_features`.
            - edge_id: <u>, <v>, <key> tuple of closest street edge.
            - edge_highway_type: Highway type of closest edge.
            - edge_importance: Betweenness centrality of closest edge.
            - dist_to_edge: Distance to closest street edge in meters.
        """
        transformer_to_meters = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

        for building_osmid, building_features in self.buildings_features.items():
            centroid = building_features["geometry"].centroid
            centroid_proj = transform(transformer_to_meters.transform, centroid)

            # query nearby edges using spatial index
            nearby_indices = self.osm_data.street_edges_tree.query(centroid.buffer(0.01))  # ~1 km buffer in degrees
            if not len(nearby_indices):
                nearby_indices = range(len(self.osm_data.street_edges))

            # find closest edge by distance
            min_dist = float("inf")
            edge_idx = None

            for idx in nearby_indices:
                edge_geom = self.osm_data.street_edges.geometry.iloc[idx]
                edge_proj = transform(transformer_to_meters.transform, edge_geom)

                dist = centroid_proj.distance(edge_proj)
                if dist < min_dist:
                    min_dist = dist
                    edge_idx = idx

            if edge_idx is not None:
                closest_edge = self.osm_data.street_edges.iloc[edge_idx]

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


    def building_nearby_facilities(self, poi_thresholds, parking_threshold):
        """
        Compute the number of points of interest -- parks, museums, and campuses -- within given distance thresholds from each building.
        Indicate if there exists a loading dock or parking amenity within a given distance threshold.

        Params:
          - poi_thresholds: List of distance thresholds in meters.
          - parking_threshold: Distance threshold in meters.

        Adds new fields for each building in `buildings_features`.
          - nearby_poi_<threshold>: PoI count for each threshold in `poi_thresholds` for each building in `buildings_dict`.
          - loading_dock: Boolean indicating whether a building has a loading dock.
          - parking_amenity: Boolean indicating whether a building has a parking amenity.
        """
        for building_features in self.buildings_features.values():
            centroid = building_features["geometry"].centroid
            lon, lat = (centroid.x, centroid.y)

        for threshold in poi_thresholds:
            degree_threshold = meters_to_degrees(threshold, lat)
            indices = self.osm_data.pois_tree.query_ball_point((lon, lat), degree_threshold)
            building_features[f"nearby_poi_{threshold}"] = len(indices)

        degree_threshold = meters_to_degrees(parking_threshold, lat)
        for key, tree in {
            "loading_dock": self.osm_data.sdz_loading_docks_tree,
            "parking_amenity": self.osm_data.sdz_parking_amenities_tree
        }.items():
            indices = tree.query_ball_point((lon, lat), degree_threshold)
            building_features[key] = len(indices) > 0