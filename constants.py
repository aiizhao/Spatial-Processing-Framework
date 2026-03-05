METERS_PER_LEVEL = 3.0
METERS_PER_DEGREE_LAT = 111320
SDZ_TYPE_TO_TAGS = {
    "university": {
        "amenity": "university",
    },
    "hospital": {
        "amenity": "hospital",
        "healthcare": "hospital"
    }
}
class TimeConstants:
    MAX_HOUR = 23
    MAX_MINUTE = 59
    DAYS_PER_WEEK = 7
    SECONDS_PER_MINUTE = 60
    HIGH_THRESHOLD = 0.95
    MED_THRESHOLD = 0.75
    HIGH_CONFIDENCE = "high"
    MED_CONFIDENCE = "med"
    LOW_CONFIDENCE = "low"