from __future__ import annotations
from datetime import datetime, date, time
from typing import List
from google import genai
from utils import *
from constants import *
import re
import json
import requests


__all__ = ["TimeInterval", "BuildingHours"]


class TimeInterval:
    """
    Represents an interval within 00:00-23:59 for any date.
    """

    interval_regex = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")

    def __init__(self, start_hour: int, start_minute: int, end_hour: int, end_minute: int):
        """
        Params:
            - start_hour: Integer in [0, 23].
            - start_minute: Integer in [0, 59].
            - end_hour: Integer in [0, 23]. Must be greater than or equal to `start_hour`.
            - end_minute: Integer in [0, 59]. Must be greater than or equal to `start_minute` if `start_hour` = `end_hour`.

        Raises:
            ValueError if any params are out-of-bounds or the interval end is before the interval start.
        """
        self.start = time(start_hour, start_minute)
        self.end = time(end_hour, end_minute)
        if self.end < self.start:
            raise ValueError("Interval end is before interval start.")


    def intersect(self, otherInterval: TimeInterval) -> TimeInterval:
        """
        Params:
            otherInterval: Any time interval.

        Returns:
            The intersection with `otherInterval`, or an empty interval 00:00-00:00 if the intervals do not intersect.
        """
        if self.end <= otherInterval.start or self.start >= otherInterval.end:
            return TimeInterval(0, 0, 0, 0)

        start = max(self.start, otherInterval.start)
        end = min(self.end, otherInterval.end)
        return TimeInterval(start.hour, start.minute, end.hour, end.minute)


    def union(self, otherInterval: TimeInterval) -> TimeInterval:
        """
        Params:
            otherInterval: Any time interval.

        Returns:
            The union with `otherInterval`, or an empty interval 00:00-00:00 if the intervals do not intersect.
        """
        if self.end <= otherInterval.start or self.start >= otherInterval.end:
            return TimeInterval(0, 0, 0, 0)

        start = min(self.start, otherInterval.start)
        end = max(self.end, otherInterval.end)
        return TimeInterval(start.hour, start.minute, end.hour, end.minute)


    def intersect_over_union(self, otherIntervals: List[TimeInterval]) -> float:
        """
        Params:
            otherIntervals: Nonempty list of time intervals.

        Returns:
            The IoU with `otherInterval`. Ratio in [0, 1] rounded to two decimal places.
        """
        intersection = self
        for otherInterval in otherIntervals:
            intersection = intersection.intersect(otherInterval)
        intersection_duration = intersection.duration()

        if intersection_duration == 0:
            return 0

        union = self
        for otherInterval in otherIntervals:
            union = union.intersect(otherInterval)
        union_duration = union.duration()

        if union_duration == 0:
            return 0

        return round(intersection_duration / union_duration, 2)


    def duration(self):
        """
        Returns:
            The number of minutes elapsed between the start and the end of the interval.
        """
        today = date.today()
        start_datetime = datetime.combine(today, self.start)
        end_datetime = datetime.combine(today, self.end)
        return (
            end_datetime - start_datetime
        ).total_seconds() / TimeConstants.SECONDS_PER_MINUTE


    def contains(self, otherInterval: TimeInterval) -> bool:
        """
        Params:
            otherInterval: Any time interval.

        Returns:
            True if `otherInterval` is fully contained within the interval, and False otherwise.
        """
        return otherInterval.start >= self.start and otherInterval.end <= self.end


    def __repr__(self) -> str:
        return f"""{self.start.strftime("%H:%M")}-{self.end.strftime("%H:%M")}"""


    def __str__(self) -> str:
        return self.__repr__()


    @staticmethod
    def from_str(interval_str: str) -> TimeInterval:
        """
        Params:
            interval_str: Either one of ["24/7", "closed", "unknown"] or a string formatted as "HH:MM-HH:MM" representing an interval within 00:00-23:59.

        Returns:
            The time interval represented by `interval_str`.
            If `interval_str` is "24/7", returns the interval 00:00-23:59.
            If `interval_str` is "unknown" or "closed", returns the empty interval 00:00-00:00.

        Raises:
            ValueError if `interval_str` does not match any of the accepted formats.
        """
        if interval_str == "24/7":
            return TimeInterval(0, 0, TimeConstants.MAX_HOUR, TimeConstants.MAX_MINUTE)
        elif interval_str == "closed" or interval_str == "unknown":
            return TimeInterval(0, 0, 0, 0)

        match = TimeInterval.interval_regex.match(interval_str)
        if not match:
            raise ValueError(f"Invalid time interval format.")

        start_hour, start_minute, end_hour, end_minute = match.groups()
        return TimeInterval(
            int(start_hour), int(start_minute), int(end_hour), int(end_minute)
        )


class BuildingHours:
    def __init__(self, sdz_name, google_api_key, gemini_api_key):
        """
        Params:
            - sdz_name: Name of a campus or institution.
            - google_api_key: Google Cloud API Key.
            - gemini_api_key: Google Gemini API Key.
        """
        self.sdz_name = sdz_name
        self.google_api_key = google_api_key
        self.gemini_api_key = gemini_api_key

    def _get_google_places_opening_hours(self, query):
        """
        Params:
            query: Input text for a Text Search Request to the Google Places API.
        
        Returns:
            regularOpeningHours object of the Place Details from the top match of the Text Search Request to the Google Places API.
            None if error occurs while querying the Google Places API.
        """
        try:
            # Query Text Search endpoint for a Place ID
            search_url = "https://places.googleapis.com/v1/places:searchText"

            search_headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.google_api_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.regularOpeningHours",
            }

            search_data = {"textQuery": query}

            search_response = requests.post(
                search_url, headers=search_headers, data=json.dumps(search_data)
            )
            search_response.raise_for_status()
            search_data = search_response.json()

            opening_hours = search_data["places"][0].get("regularOpeningHours", {})
            return opening_hours.get("periods", None)

        except requests.exceptions.HTTPError as error:
            print(error)

        except:
            pass


    def _parse_google_places_opening_hours(self, opening_hours):
        """
        Params:
            opening_hours: regularOpeningHours object from a Google Places API response.
        
        Returns:
            Representation of `opening_hours` as an ordered list of TimeIntervals; one interval per day from Sunday to Saturday.
        """
        intervals = [
            TimeInterval.from_str("closed") for day in range(TimeConstants.DAYS_PER_WEEK)
        ]

        for interval in opening_hours:
            if "close" not in interval:
                return [
                    TimeInterval.from_str("24/7")
                    for day in range(TimeConstants.DAYS_PER_WEEK)
                ]
            elif interval["open"]["day"] != interval["close"]["day"]:
                intervals[interval["open"]["day"]] = TimeInterval(
                    interval["open"]["hour"],
                    interval["open"]["minute"],
                    TimeConstants.MAX_HOUR,
                    TimeConstants.MAX_MINUTE,
                )
            else:
                # TODO: handle special case of multiple intervals per day
                intervals[interval["open"]["day"]] = TimeInterval(
                    interval["open"]["hour"],
                    interval["open"]["minute"],
                    interval["close"]["hour"],
                    interval["close"]["minute"],
                )

        return intervals
    

    def _get_gemini_building_hours(self, prompt):
        """
        Params:
            prompt: LLM prompt for building hours and/or delivery windows.

        Returns: Building hours dict.
            {
                "opening_hours": {0: <TimeInterval>, ..., 6: <TimeInterval>},
                "delivery_window": {...},
            }
        Raises:
            ValueError if error occurs while querying the Gemini API or parsing the response.
        """
        try:
            client = genai.Client(api_key=self.gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite", contents=prompt
            )
            content = response.text
            return json.loads(content[7:-3])

        except:
            raise ValueError("Failed to query and parse Gemini 2.5 Flash-Lite response.")


    def get_building_hours(self, delivery_location_name, delivery_location_address):
        """
        Params:
            - delivery_location_name: List of delivery location name within the SDZ.
            - delivery_location_addresses: List of corresponding delivery location address within the SDZ.

        Returns: Building hours dict; for each list value in the dict, indices represent days of the week from Sunday to Saturday.
            {
                "opening_hours": [<TimeInterval>, ...],
                "delivery_window": [<TimeInterval>, ...]
            }
        """
        google_places_opening_hours = self._get_google_places_opening_hours(self.sdz_name + delivery_location_name)
        prompt = building_hours_prompt(delivery_location_name, delivery_location_address)
        gemini_response = self._get_gemini_building_hours(prompt)

        if google_places_opening_hours is not None:
            opening_hours_interval_list = self._parse_google_places_opening_hours(google_places_opening_hours)
        else:
            opening_hours_interval_list = gemini_response["opening_hours"]
        delivery_window_interval_list = gemini_response["delivery_window"]

        return {
            "opening_hours": opening_hours_interval_list,
            "delivery_window": delivery_window_interval_list,
        }
