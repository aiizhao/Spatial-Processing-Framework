import os
import pickle
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.strtree import STRtree
from utils import make_feature_tree


__all__ = ["OpenStreetMapDataLoader"]


ox.settings.useful_tags_way = [
    "name",
    "highway",
    "maxspeed",
    "parking:both",
    "parking:both:fee",
    "parking:both:access",
    "parking:both:maxstay"
]


class OpenStreetMapDataLoader:
    def __init__(self, sdz: str, place: str, data_path: str):
        """
        Params:
            - sdz: Name of a campus or institution.
            - place: City, state, country the SDZ is located in.
            - data_path: Relative filepath location to store data fetched from OSM as .pkl files.
        """
        self.sdz = sdz
        self.place = place
        self.data_path = data_path
        self.sdz_boundary = None
        self.sdz_buildings = None
        self.g_walking = None
        self.g_driving = None
        self.edge_centralities = None
        self.walking_street_nodes = None
        self.walking_street_edges = None
        self.street_edges = None
        self.street_edges_tree = None
        self.street_intersections = None
        self.street_intersections_tree = None
        self.pois_tree = None
        self.sdz_loading_docks_tree = None
        self.sdz_parking_amenities_tree = None
        self.sdz_parking_edges = None


    def _get_buildings(self):
        sdz_gdf = ox.geocode_to_gdf(f"{self.sdz}, {self.place}")
        self.sdz_boundary = sdz_gdf.loc[0, "geometry"]

        sdz_buildings = ox.features_from_place(f"{self.sdz}, {self.place}", tags={"building": True})
        self.sdz_buildings = sdz_buildings.reset_index(drop=False)

        print("Building Data Retrieved")


    def _get_street_network(self):
        g_walking = ox.graph_from_place(self.place, network_type="walk")
        self.g_walking = ox.distance.add_edge_lengths(g_walking)

        self.g_driving = ox.graph_from_place(self.place, network_type="drive")
        self.edge_centralities = nx.edge_betweenness_centrality(self.g_driving, weight="length")
        nx.set_edge_attributes(self.g_driving, self.edge_centralities, "importance")

        self.walking_street_nodes, self.walking_street_edges = ox.graph_to_gdfs(self.g_walking)
        street_nodes, street_edges = ox.graph_to_gdfs(self.g_driving)

        self.street_edges = street_edges.reset_index(drop=False)
        self.street_edges_tree = STRtree(self.street_edges.geometry)

        street_intersections = street_nodes[street_nodes["street_count"] > 1]
        self.street_intersections = street_intersections.reset_index(drop=False)
        self.street_intersections_tree = STRtree(self.street_intersections.geometry)

        print("Street Network Data Retrieved")


    def _get_pois(self):
        try:
            pois = ox.features_from_place(self.place, tags={
                "leisure": "park",
                "tourism": "museum",
                "amenity": ["university", "college"]
            })
        except:
            pois = gpd.GeoDataFrame(geometry=[])
        self.pois_tree = make_feature_tree(pois)

        print("Points of Interest Data Retrieved")


    def _get_loading_docks(self):
        try:
            sdz_loading_docks = ox.features_from_place(self.sdz, tags={"amenity": "loading_dock"})
        except:
            sdz_loading_docks = gpd.GeoDataFrame(geometry=[])
        self.sdz_loading_docks_tree = make_feature_tree(sdz_loading_docks)

        print("Loading Dock Data Retrieved")


    def _get_parking_amenities(self):
        try:
            sdz_parking_amenities = ox.features_from_place(self.sdz, tags={
                "amenity": "parking",
                "fee": True,
                "access": True,
                "maxstay": True,
            })
        except:
            sdz_parking_amenities = gpd.GeoDataFrame(geometry=[])
        self.sdz_parking_amenities_tree = make_feature_tree(sdz_parking_amenities)
        self.sdz_parking_edges = self.street_edges[(self.street_edges["parking:both"].notna()) | (self.street_edges["highway"] == "residential")]

        print("Parking Amenity Data Retrieved")


    def save_data(self):
        self._get_buildings()
        self._get_street_network()
        self._get_pois()
        self._get_loading_docks()
        self._get_parking_amenities()

        for key, object in self.__dict__.items():
            if key not in ["sdz", "place", "data_path"]:
                with open(f"{self.data_path}/{key}.pkl", "wb") as file:
                    pickle.dump(object, file)

    
    def load_data(self):
        for filename in os.listdir(self.data_path):
            if filename.endswith(".pkl") and filename[:-4] in self.__dict__:
                with open(os.path.join(self.data_path, filename), "rb") as f:
                    self.__dict__[filename[:-4]] = pickle.load(f)
