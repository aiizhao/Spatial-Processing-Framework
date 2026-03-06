# Spatial Processing Framework

This package analyzes the buildings and surrounding area of a given "Special Delivery Zone," focusing on university or hospital campuses. It provides insights into campus infrastructure, parking accessibility, and points of interest.

## Getting Started

Install the required Python packages:

```bash
pip install numpy pandas osmnx networkx shapely pyproj geopy geopandas scipy tqdm google
```

---

## Section Overview

| Class | Description |
|---|---|
| `OpenStreetMapDataLoader` | Fetches and preprocesses OpenStreetMap data, including buildings, roads, and points of interest, for the specified location and SDZ |
| `BuildingFeatures` | Calculates various features for each building within the SDZ, such as height, area, proximity to intersections and street edges, and nearby points of interest |
| `StreetParking` | Identifies the closest street parking options to a given building within the SDZ |
| `BuildingHours` | Uses LLM and Google Places API to extract building opening hours and ideal delivery windows for specific delivery locations within the SDZ |
| Utility Functions | Defines functions used for geographical calculations and data manipulation |

---

## OSM Data Loader

The `OpenStreetMapDataLoader` class fetches and caches the following datasets as `.pkl` files to the specified `data_path`:

| Attribute | Description |
|---|---|
| `sdz_boundary` | Polygon boundary of the SDZ campus or institution |
| `sdz_buildings` | GeoDataFrame of all buildings within the SDZ |
| `g_walking` | Walking street network graph with edge lengths |
| `g_driving` | Driving street network graph with edge betweenness centrality |
| `edge_centralities` | Betweenness centrality scores for all driving edges |
| `walking_street_nodes` | Nodes GeoDataFrame of the walking network |
| `walking_street_edges` | Edges GeoDataFrame of the walking network |
| `street_edges` | Edges GeoDataFrame of the driving network |
| `street_edges_tree` | STRtree spatial index over driving street edges |
| `street_intersections` | Nodes with `street_count` > 1 |
| `street_intersections_tree` | STRtree spatial index over intersections |
| `pois_tree` | STRtree spatial index over nearby parks, museums, universities, and colleges |
| `sdz_loading_docks_tree` | STRtree spatial index over loading dock amenities within the SDZ |
| `sdz_parking_amenities_tree` | STRtree spatial index over parking amenities within the SDZ |
| `sdz_parking_edges` | Street edges GeoDataFrame with on-street parking tags or residential highway type |

Call `save_data()` to fetch from OSM and write all `.pkl` files, or `load_data()` to restore previously saved data.

---

## Building Features

The `BuildingsData` class computes the following features for each building, stored in `buildings_features` keyed by OSM ID.

### Base Attributes

Computed on initialization:

| Field | Description |
|---|---|
| `name` | Building name from OSM tags |
| `height` | Height in meters via `height` tag, or estimated from `building:levels` × 3.0 m/level |
| `area` | Footprint area in m² |
| `geometry` | Shapely geometry of the building footprint |
| `number` | Building number via `addr:housenumber` |
| `street` | Street address via `addr:street` |
| `city` | City via `addr:city` |
| `state` | State via `addr:state` |
| `country` | Country via `addr:country` |

### Nearest Intersection

`building_closest_intersection()`

| Field | Description |
|---|---|
| `intersection_osmid` | OSM ID of the nearest street intersection |
| `intersection_deg` | Degree of the nearest intersection |
| `dist_to_intersection` | Distance to the nearest intersection in meters |

### Nearest Street Edge

`building_closest_edge()`

| Field | Description |
|---|---|
| `edge_id` | `(u, v, key)` tuple identifying the closest street edge |
| `edge_highway_type` | OSM highway classification of that edge |
| `edge_importance` | Betweenness centrality score of that edge |
| `dist_to_edge` | Distance to the nearest street edge in meters |

### Nearby Facilities

`building_nearby_facilities()`

| Field | Description |
|---|---|
| `nearby_poi_<threshold>` | Count of parks, museums, and campuses within each `poi_threshold` meters |
| `loading_dock` | `True` i.f.f. a loading dock amenity exists within `parking_threshold` meters |
| `parking_amenity` | `True` i.f.f. a parking amenity exists within `parking_threshold` meters |

---

## Street Parking

The `StreetParking` class identifies the closest street parking option to a given building by walking route distance.

### `get_closest_parking()`

| Param | Description |
|---|---|
| `building_features` | `BuildingFeatures` object for the target building |
| `parking_threshold` | Maximum great-circle distance in meters to consider a parking edge as a candidate |

Returns a tuple of three values:

| Return Value | Description |
|---|---|
| `closest_parking` | The closest street edge with on-street parking or the building's nearest street edge as a fallback if no parking edges are within threshold |
| `shortest_route` | Ordered list of OSM node IDs forming the shortest walking route from the building centroid to the closest point on the parking edge; `None` if no route is found |
| `min_dist` | Walking route distance in meters to the closest parking edge; `float("inf")` if unreachable |

Parking edges tagged with `parking:both = no` are excluded from consideration. If no qualifying parking edge is found within the threshold, the method falls back to the building's pre-computed closest street edge from `building_closest_edge()`.

---

## Building Hours

The `BuildingHours` class retrieves opening hours and delivery windows for specific buildings within the SDZ, combining the Google Places API with the Gemini LLM.

### Initialization

| Param | Description |
|---|---|
| `sdz_name` | Name of the campus or institution, prepended to Place search queries |
| `google_api_key` | Google Cloud API key for the Places API |
| `gemini_api_key` | Google Gemini API key |

### `get_building_hours()`

Fetches opening hours from the Google Places API Text Search and delivery window estimates from Gemini 2.5 Flash-Lite, then merges the results.

| Param | Description |
|---|---|
| `delivery_location_name` | Name of the delivery location within the SDZ |
| `delivery_location_address` | Street address of the delivery location |

Returns a dict with two keys, each containing an ordered list of `TimeInterval` objects — one per day of the week from Sunday (0) to Saturday (6):

| Key | Source | Description |
|---|---|---|
| `opening_hours` | Google Places API, falls back to Gemini | The regular opening hours of the location |
| `delivery_window` | Gemini 2.5 Flash-Lite | The recommended delivery window for the location |

`TimeInterval` objects support the following values:

| Value | Represents |
|---|---|
| `"HH:MM-HH:MM"` | Interval from start to end time |
| `"24/7"` | Full-day interval `00:00-23:59` |
| `"closed"` | Empty interval `00:00-00:00` |
| `"unknown"` | Cannot be determined |
