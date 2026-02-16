class DownloadOpenStreetMapData:
    def get_buildings(sdz, place):
        SDZ_GDF = ox.geocode_to_gdf(f"{sdz}, {place}")
        SDZ_BOUNDARY = SDZ_GDF.loc[0, "geometry"]

        BUILDINGS = ox.features_from_place(place, tags={"building": True})
        BUILDINGS = BUILDINGS.reset_index(drop=False)
        BUILDINGS_TREE = STRtree(BUILDINGS.geometry)

        SDZ_BUILDINGS = ox.features_from_place(f"{sdz}, {place}", tags={"building": True})
        SDZ_BUILDINGS = SDZ_BUILDINGS.reset_index(drop=False)

    def get_street_network_walking(place):
        G_WALKING = ox.graph_from_place(place, network_type="walk")
        G_WALKING = ox.distance.add_edge_lengths(G_WALKING)

    def get_street_network_driving(place):
        G_DRIVING = ox.graph_from_place(place, network_type="drive")
        EDGE_CENTRALITIES = nx.edge_betweenness_centrality(G_DRIVING, weight="length")
        nx.set_edge_attributes(G_DRIVING, EDGE_CENTRALITIES, "importance")

    def get_street_network_tree():
        WALKING_STREET_NODES, WALKING_STREET_EDGES = ox.graph_to_gdfs(G_WALKING)
        STREET_NODES, STREET_EDGES = ox.graph_to_gdfs(G_DRIVING)

        STREET_EDGES = STREET_EDGES.reset_index(drop=False)
        STREET_EDGES_TREE = STRtree(STREET_EDGES.geometry)

        STREET_INTERSECTIONS = STREET_NODES[STREET_NODES["street_count"] > 1]
        STREET_INTERSECTIONS = STREET_INTERSECTIONS.reset_index(drop=False)
        STREET_INTERSECTIONS_TREE = STRtree(STREET_INTERSECTIONS.geometry)

    def get_pois(place):
        try:
            POIS = ox.features_from_place(place, tags={
                "leisure": "park",
                "tourism": "museum",
                "amenity": ["university", "college"]
            })
        except:
            POIS = gpd.GeoDataFrame(geometry=[])
            POIS_TREE = make_feature_tree(POIS)

    def get_loading_docks(place):
        try:
            SDZ_LOADING_DOCKS = ox.features_from_place(SDZ, tags={"amenity": "loading_dock"})
        except:
            SDZ_LOADING_DOCKS = gpd.GeoDataFrame(geometry=[])
            SDZ_LOADING_DOCKS_TREE = make_feature_tree(SDZ_LOADING_DOCKS)

    def get_parking_amenities(place):
        try:
            SDZ_PARKING_AMENITIES = ox.features_from_place(SDZ, tags={
                "amenity": "parking",
                "fee": True,
                "access": True,
                "maxstay": True,
            })
        except:
            SDZ_PARKING_AMENITIES = gpd.GeoDataFrame(geometry=[])
            SDZ_PARKING_AMENITIES_TREE = make_feature_tree(SDZ_PARKING_AMENITIES)
            SDZ_PARKING_EDGES = STREET_EDGES[(STREET_EDGES["parking:both"].notna()) | (STREET_EDGES["highway"] == "residential")]