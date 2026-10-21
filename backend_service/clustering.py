"""Geospatial clustering utilities for defect deduplication.

Uses the Haversine great-circle distance formula to identify and cluster
repeated pothole observations occurring within a 5-meter radius.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

EARTH_RADIUS_METERS: float = 6371000.0


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculates the great-circle distance between two geographic points in meters.

    Args:
        lat1: Latitude of point 1 in decimal degrees.
        lon1: Longitude of point 1 in decimal degrees.
        lat2: Latitude of point 2 in decimal degrees.
        lon2: Longitude of point 2 in decimal degrees.

    Returns:
        Distance in meters.
    """
    # Convert decimal degrees to radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    # Ensure numerical stability within [-1.0, 1.0]
    a = max(0.0, min(1.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_METERS * c


def find_nearby_cluster(
    latitude: float,
    longitude: float,
    candidate_records: Iterable[Dict[str, Any]],
    radius_meters: float = 5.0,
) -> Optional[Tuple[Dict[str, Any], float]]:
    """Locates the nearest existing pothole record within a specified radius.

    Args:
        latitude: New detection latitude.
        longitude: New detection longitude.
        candidate_records: Existing records to check against.
        radius_meters: Maximum clustering distance threshold (default: 5.0m).

    Returns:
        Tuple of (closest_record, distance_meters) or None if no record is within radius.
    """
    closest_record: Optional[Dict[str, Any]] = None
    min_dist: float = float("inf")

    for record in candidate_records:
        r_lat = record.get("latitude")
        r_lon = record.get("longitude")

        if r_lat is None or r_lon is None:
            # Check nested location structure if present
            loc = record.get("location")
            if isinstance(loc, dict):
                r_lat = loc.get("latitude")
                r_lon = loc.get("longitude")
            elif isinstance(loc, (list, tuple)) and len(loc) >= 2:
                r_lat, r_lon = loc[0], loc[1]

        if r_lat is None or r_lon is None:
            continue

        dist = haversine_distance(latitude, longitude, float(r_lat), float(r_lon))
        if dist <= radius_meters and dist < min_dist:
            min_dist = dist
            closest_record = record

    if closest_record is not None:
        return closest_record, round(min_dist, 2)
    return None


def cluster_potholes(
    records: List[Dict[str, Any]], eps_meters: float = 5.0
) -> List[Dict[str, Any]]:
    """Aggregates a list of raw defect records into spatial clusters.

    Useful for generating consolidated municipal map pins and work-order batches.

    Args:
        records: List of raw defect dictionaries.
        eps_meters: Maximum link distance for cluster grouping.

    Returns:
        List of cluster dictionaries containing cluster centroids, constituent
        records count, and highest defect severity.
    """
    severity_rank = {"High": 3, "Medium": 2, "Low": 1}
    clusters: List[Dict[str, Any]] = []

    for item in records:
        lat = item.get("latitude")
        lon = item.get("longitude")
        if lat is None or lon is None:
            continue

        matched_cluster = None
        for cluster in clusters:
            dist = haversine_distance(
                lat, lon, cluster["latitude"], cluster["longitude"]
            )
            if dist <= eps_meters:
                matched_cluster = cluster
                break

        if matched_cluster:
            matched_cluster["records"].append(item)
            matched_cluster["detection_count"] += 1
            # Update centroid with rolling average
            n = matched_cluster["detection_count"]
            matched_cluster["latitude"] = round(
                (matched_cluster["latitude"] * (n - 1) + lat) / n, 6
            )
            matched_cluster["longitude"] = round(
                (matched_cluster["longitude"] * (n - 1) + lon) / n, 6
            )

            # Escalate severity if new detection is higher
            item_sev = item.get("severity", "Low").capitalize()
            cur_sev = matched_cluster["severity"]
            if severity_rank.get(item_sev, 0) > severity_rank.get(cur_sev, 0):
                matched_cluster["severity"] = item_sev
        else:
            clusters.append(
                {
                    "cluster_id": item.get("cluster_id") or f"cl_{len(clusters)+1}",
                    "latitude": lat,
                    "longitude": lon,
                    "severity": item.get("severity", "Low").capitalize(),
                    "status": item.get("status", "reported"),
                    "detection_count": 1,
                    "records": [item],
                }
            )

    return clusters
