# -*- coding: utf-8 -*-
"""GeoJSON 读取和几何拆分。"""

import json


def load_geojson(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_feature_geometries(data):
    """
    把 FeatureCollection / Feature / Geometry
    统一转换成 geometry 字典。
    """
    obj_type = data.get("type")

    if obj_type == "FeatureCollection":
        for feature in data.get("features", []):
            geometry = feature.get("geometry")
            if geometry:
                yield geometry
        return

    if obj_type == "Feature":
        geometry = data.get("geometry")
        if geometry:
            yield geometry
        return

    # 直接就是 Geometry
    yield data


def geometry_types(data):
    result = set()

    def collect(geom):
        gtype = geom.get("type")

        if gtype == "GeometryCollection":
            for child in geom.get("geometries", []):
                collect(child)
        elif gtype:
            result.add(gtype)

    for geom in iter_feature_geometries(data):
        collect(geom)

    return result


def iter_polygons(data):
    """
    每次返回一个 Polygon 的 rings：
    [
      outer_ring,
      hole_ring_1,
      ...
    ]
    """
    def walk(geom):
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])

        if gtype == "Polygon":
            yield coords

        elif gtype == "MultiPolygon":
            for polygon in coords:
                yield polygon

        elif gtype == "GeometryCollection":
            for child in geom.get("geometries", []):
                yield from walk(child)

    for geom in iter_feature_geometries(data):
        yield from walk(geom)


def iter_lines(data):
    """每次返回一个 LineString 坐标数组。"""
    def walk(geom):
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])

        if gtype == "LineString":
            yield coords

        elif gtype == "MultiLineString":
            for line in coords:
                yield line

        elif gtype == "GeometryCollection":
            for child in geom.get("geometries", []):
                yield from walk(child)

    for geom in iter_feature_geometries(data):
        yield from walk(geom)


def iter_points(data):
    """每次返回一个 Point 坐标。"""
    def walk(geom):
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])

        if gtype == "Point":
            yield coords

        elif gtype == "MultiPoint":
            for point in coords:
                yield point

        elif gtype == "GeometryCollection":
            for child in geom.get("geometries", []):
                yield from walk(child)

    for geom in iter_feature_geometries(data):
        yield from walk(geom)


def remove_closing_duplicate(ring):
    """
    Polygon 首尾通常重复。
    Geometry Script 不需要重复终点。
    """
    if len(ring) >= 2 and ring[0][0] == ring[-1][0] and ring[0][1] == ring[-1][1]:
        return ring[:-1]
    return ring


def remove_consecutive_duplicates(points):
    result = []

    for p in points:
        if not result:
            result.append(p)
            continue

        last = result[-1]

        if p[0] != last[0] or p[1] != last[1]:
            result.append(p)

    return result
