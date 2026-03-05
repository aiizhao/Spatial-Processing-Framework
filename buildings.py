import networkx as nx
import numpy as np
import pandas as pd
from geopy.distance import geodesic
from scipy.spatial import cKDTree
from shapely.geometry import Point
from shapely.ops import transform
from pyproj import Transformer
from tqdm import tqdm
from utils import *
from constants import *


class BuildingFeatures:
    def __init__(self):
        self.name = None
        self.height = None
        self.area = None
        self.geometry = None
        self.number = None
        self.street = None
        self.city = None
        self.state = None
        self.country = None
        self.intersection_osmid = None
        self.intersection_deg = None
        self.dist_to_intersection = None
        self.edge_id = None
        self.edge_importance = None
        self.edge_highway_type = None
        self.dist_to_edge = None
        self.nearby_pois = dict()
        self.loading_dock = None
        self.parking_amenity = None


class BuildingsData:
    def __init__(self, osm_data):
        """
        Params: 
            osm_data: OpenStreetMapDataLoader wiht non-None fields.
        """
        self.osm_data = osm_data
        self.sdz_building_features = dict()

        print("Initializing Building Features")
        for _, row in tqdm(self.osm_data.sdz_buildings.iterrows(), total=len(self.osm_data.sdz_buildings)):
            osmid = row["id"]
            height, area = self._building_dimensions(row)

            self.sdz_building_features[osmid] = BuildingFeatures()
            self.sdz_building_features[osmid].name = row.get("name", float("nan"))
            self.sdz_building_features[osmid].height = height
            self.sdz_building_features[osmid].area = area
            self.sdz_building_features[osmid].geometry = row["geometry"]
            self.sdz_building_features[osmid].number = row.get("addr:housenumber", float("nan"))
            self.sdz_building_features[osmid].street = row.get("addr:street", float("nan"))
            self.sdz_building_features[osmid].city = row.get("addr:city", float("nan"))
            self.sdz_building_features[osmid].state = row.get("addr:state", float("nan"))
            self.sdz_building_features[osmid].country = row.get("addr:country", float("nan"))


    def _building_dimensions(self, building):
        # check "height" and "building:levels" tags
        try:
            height = float(str(building["height"]).replace("m", ""))
        except:
            try:
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
        intersection_x, intersection_y = transformer_to_meters.transform(intersection_lons, intersection_lats)
        tree = cKDTree(np.column_stack([intersection_x, intersection_y]))

        for building_features in self.sdz_building_features.values():
            centroid = building_features.geometry.centroid
            centroid_x, centroid_y = transformer_to_meters.transform(centroid.x, centroid.y)
            dist, idx = tree.query([centroid_x, centroid_y])

            building_features.intersection_osmid = int(intersection_osmids[idx])
            building_features.intersection_deg = int(intersection_degs[idx])
            building_features.dist_to_intersection = float(dist)


    def building_closest_edge(self):
        """
        Compute the closest street edge for each building.

        Adds three fields for each building in `buildings_features`.
            - edge_id: <u>, <v>, <key> tuple of closest street edge.
            - edge_highway_type: Highway type of closest edge.
            - edge_importance: Betweenness centrality of closest edge.
            - dist_to_edge: Distance to closest street edge in meters.
        """
        for _, building_features in self.sdz_building_features.items():
            centroid = building_features.geometry.centroid
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
                building_features.edge_id = edge_id

                highway = closest_edge.get("highway", float("nan"))
                if isinstance(highway, list):
                    building_features.edge_highway_type = highway[0] if highway else float("nan")
                else:
                    building_features.edge_highway_type = highway

                building_features.edge_importance = closest_edge.get("importance", float("nan"))
                building_features.dist_to_edge = float(min_dist)


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
        for building_features in self.sdz_building_features.values():
            centroid = building_features.geometry.centroid
            lon, lat = (centroid.x, centroid.y)

            for threshold in poi_thresholds:
                degree_threshold = meters_to_degrees(threshold, lat)
                indices = self.osm_data.pois_tree.query_ball_point((lon, lat), degree_threshold)
                building_features.nearby_pois[threshold] = len(indices)

            degree_threshold = meters_to_degrees(parking_threshold, lat)
            for key, tree in {
                "loading_dock": self.osm_data.sdz_loading_docks_tree,
                "parking_amenity": self.osm_data.sdz_parking_amenities_tree
            }.items():
                indices = tree.query_ball_point((lon, lat), degree_threshold)
                building_features.__dict__[key] = len(indices) > 0


    def building_dataframe(self):
        sdz_building_features_dict = dict()
        for osmid, building_features in self.sdz_building_features.items():
            building_features_dict = building_features.__dict__.copy()
            nearby_pois = building_features_dict.pop("nearby_pois")
            for threshold in building_features.nearby_pois:
                building_features_dict[f"nearby_poi_{threshold}"] = nearby_pois[threshold]
            sdz_building_features_dict[osmid] = building_features_dict

        df = pd.DataFrame.from_dict(sdz_building_features_dict, orient="index")
        df.index.name = "OSM_ID"
        return df


class StreetParking:
    def __init__(self, osm_data):
        """
        Params
            osm_data: OpenStreetMapDataLoader wiht non-None fields.
        """
        self.osm_data = osm_data


    def _walking_distance(self, src_lat, src_lon, dst_lat, dst_lon, threshold):
        """
        Returns:
            Shortest walking route and route distance in meters between (src_lat, src_lon) and (dst_lat, dst_lon).
            (None, INF) if geodesic distance exceeds `threshold` meters.
        """
        gdc_m = geodesic((dst_lat, dst_lon), (src_lat, src_lon)).meters
        if gdc_m >= threshold:
            return None, float("inf")

        src_node = ox.distance.nearest_nodes(self.osm_data.g_walking, src_lon, src_lat)
        dst_node = ox.distance.nearest_nodes(self.osm_data.g_walking, dst_lon, dst_lat)
        if src_node is None or dst_node is None or not nx.has_path(self.osm_data.g_walking, src_node, dst_node):
            return None, float("inf")

        walking_route = nx.shortest_path(self.osm_data.g_walking, src_node, dst_node, weight="length")
        walking_m = nx.path_weight(self.osm_data.g_walking, walking_route, weight="length")

        return walking_route, int(walking_m)


    def _street_edge_walking_distance(self, lat, lon, edge, threshold):
        """
        Returns:
            Shortest walking route distance in meters between (lat, lon) and the closest point on the input edge.
            (None, INF) if geodesic distance exceeds `threshold` meters.
        """
        if "parking:both" in edge and edge["parking:both"] == "no":
            return None, float("inf")

        closest_point = edge.geometry.interpolate(edge.geometry.project(Point(lon, lat)))
        return self._walking_distance(closest_point.y, closest_point.x, lat, lon, threshold)


    def get_closest_parking(self, building_features, parking_threshold):
        """
        Params:
            - building_features: #TODO
            - parking_threshold: #TODO

        Returns: A tuple containing
            - The closest street edge from the centroid of the input geometry by walking route distance; None if no street edges are within the greact circle distance threshold.
            - The associated walking route; None if the closest street edge is None.
            - The associated walking route distance; float("inf") if the closest street edge is None.
        """
        lat, lon = building_features.geometry.centroid.y, building_features.geometry.centroid.x

        closest_parking = None
        shortest_route = None
        min_dist = float("inf")

        for _, edge in self.osm_data.sdz_parking_edges.iterrows():
            route, dist = self._street_edge_walking_distance(lat, lon, edge, parking_threshold)
            if dist < min_dist:
                closest_parking = edge
                shortest_route = route
                min_dist = dist

        if closest_parking is None: # default to closest street edge
            u, v, key = building_features.edge_id
            edge = self.osm_data.street_edges[
                (self.osm_data.street_edges["u"] == u) &
                (self.osm_data.street_edges["v"] == v) &
                (self.osm_data.street_edges["key"] == key)
            ]
            closest_parking = edge.iloc[0] if not edge.empty else None
            shortest_route, min_dist = self._street_edge_walking_distance(lat, lon, closest_parking, float("inf"))

        return closest_parking, shortest_route, min_dist


if __name__ == "__main__":
    from osm import OpenStreetMapDataLoader
    data = OpenStreetMapDataLoader("MIT", "Cambridge, MA, USA", "data")
    data.load_data()
    buildings = BuildingsData(data)
    building_features = buildings.sdz_building_features[980722694]
    street_parking = StreetParking(data)
    closest_parking, shortest_route, min_dist = street_parking.get_closest_parking(building_features, 100)
    print(closest_parking)
    # buildings.building_closest_intersection()s
    # buildings.building_closest_edge()
    # buildings.building_nearby_facilities([50, 100], 100)
    # buildings.building_dataframe().to_csv("test.csv")
