## Spatial Processing Framework

This package analyzes the buildings and surrounding area of a given university or hospital campus. It provides insights into campus infrastructure, accessibility, and points of interest. 

## Getting Started

### Setup

To run, you need to install the following Python packages:
```
!pip install numpy scipy shapely pyproj tqdm osmnx networkx geopandas
```

### API Keys

*   For the **Building Hours** section, add a key titled `GEMINI_API_KEY` in the .env and enter a usable API key for Google Gemini.
*   Also for the **Building Hours** section, add a key titled `GOOGLE_API_KEY` in the .env and enter a usable API key for Google Cloud.

## Section Overview

*   **OSM Data Loader**: Fetches and preprocesses OpenStreetMap data, including buildings, roads, and points of interest, for the specified location and SDZ.
*   **Building Features**: Calculates various features for each building within the SDZ, such as height, area, proximity to intersections and street edges, and nearby points of interest.
*   **Street Parking**: Identifies the closest street parking options to a given building within the SDZ and visualizes the shortest walking route.
*   **Building Hours**: Uses LLM and Google Places API to extract building opening hours and ideal delivery windows for specific delivery locations within the SDZ.
*   **Utility Functions**: Defines functions used for geographical calculations and data manipulation.

### OSM Data Loader

The `OpenStreetMapDataLoader` class fetches and caches the following datasets as `.pkl` files to `data_path`:

| Attribute | Description |
|---|---|
| `sdz_boundary` | Polygon boundary of the SDZ (campus/institution) |
| `sdz_buildings` | GeoDataFrame of all buildings within the SDZ |
| `g_walking` | Walking street network graph with edge lengths |
| `g_driving` | Driving street network graph with edge betweenness centrality (`importance`) |
| `edge_centralities` | Betweenness centrality scores for all driving edges |
| `walking_street_nodes` | Nodes GeoDataFrame of the walking network |
| `walking_street_edges` | Edges GeoDataFrame of the walking network |
| `street_edges` | Edges GeoDataFrame of the driving network, with a spatial index |
| `street_edges_tree` | STRtree spatial index over driving street edges |
| `street_intersections` | Nodes with `street_count > 1` (true intersections) |
| `street_intersections_tree` | STRtree spatial index over intersections |
| `pois_tree` | Spatial index over nearby parks, museums, universities, and colleges |
| `sdz_loading_docks_tree` | Spatial index over loading dock amenities within the SDZ |
| `sdz_parking_amenities_tree` | Spatial index over parking amenities within the SDZ |
| `sdz_parking_edges` | Street edges with on-street parking tags or residential highway type |

Call `save_data()` to fetch from OSM and write all `.pkl` files, or `load_data()` to restore a previously saved session.

### Building Features

The `BuildingsData` class computes the following features for each building, stored in `buildings_features` keyed by OSM ID:

**Base attributes** (computed on initialization):

| Field | Description |
|---|---|
| `name` | Building name from OSM tags |
| `height` | Height in meters — from `height` tag, or estimated from `building:levels` × 3.0 m/level |
| `area` | Footprint area in m², computed in EPSG:3857 (metric projection) |
| `geometry` | Shapely geometry of the building footprint |
| `street` | Street address (`addr:street`) |
| `city` | City (`addr:city`) |
| `state` | State (`addr:state`) |
| `country` | Country (`addr:country`) |

**Nearest intersection** (via `building_closest_intersection()`):

| Field | Description |
|---|---|
| `intersection_osmid` | OSM ID of the nearest street intersection |
| `intersection_deg` | Degree (number of connected streets) of that intersection |
| `dist_to_intersection` | Distance to the nearest intersection in meters |

**Nearest street edge** (via `building_closest_edge()`):

| Field | Description |
|---|---|
| `edge_id` | `(u, v, key)` tuple identifying the closest street edge |
| `edge_highway_type` | OSM highway classification of that edge (e.g. `residential`, `primary`) |
| `edge_importance` | Betweenness centrality score of that edge |
| `dist_to_edge` | Distance to the nearest street edge in meters |

**Nearby facilities** (via `building_nearby_facilities(poi_thresholds, parking_threshold)`):

| Field | Description |
|---|---|
| `nearby_poi_<threshold>` | Count of parks, museums, and campuses within each distance threshold (meters) |
| `loading_dock` | `True` if a loading dock amenity exists within `parking_threshold` meters |
| `parking_amenity` | `True` if a parking amenity exists within `parking_threshold` meters |