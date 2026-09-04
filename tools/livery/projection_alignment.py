from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .portable_mesh_converter import LocalProjectionMesh


SLOT_GEOMETRY_SIDES = (0, 1, 2, 4, 3, 5, 6, 7, 8, 10, 9)
LONG_EDGE = 256
MIN_EDGE = 32
SCALE_MINIMUM = 0.85
SCALE_MAXIMUM = 1.15
OFFSET_LIMIT = 0.08
MINIMUM_COST_IMPROVEMENT = 0.05


@dataclass(frozen=True)
class ProjectionAlignment:
    scale_x: float = 1.0
    scale_y: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    pivot_x: float = 0.5
    pivot_y: float = 0.5


def _boundary_indices(image: np.ndarray) -> np.ndarray:
    inside = np.asarray(image, dtype=bool)
    if inside.ndim != 2:
        raise ValueError("projection alignment images must be two-dimensional")
    padded = np.pad(inside, 1, mode="constant", constant_values=False)
    boundary = inside & (
        ~padded[1:-1, :-2]
        | ~padded[1:-1, 2:]
        | ~padded[:-2, 1:-1]
        | ~padded[2:, 1:-1]
    )
    return np.flatnonzero(boundary)


def _distance_field(boundary: np.ndarray, width: int, height: int, limit: float) -> np.ndarray:
    distance = np.full((height, width), limit, dtype=np.float32)
    if boundary.size:
        distance.reshape(-1)[boundary] = 0.0
    diagonal = math.sqrt(2.0)
    for y in range(height):
        for x in range(width):
            value = distance[y, x]
            if x:
                value = min(value, float(distance[y, x - 1]) + 1.0)
            if y:
                value = min(value, float(distance[y - 1, x]) + 1.0)
                if x:
                    value = min(value, float(distance[y - 1, x - 1]) + diagonal)
                if x + 1 < width:
                    value = min(value, float(distance[y - 1, x + 1]) + diagonal)
            distance[y, x] = value
    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            value = distance[y, x]
            if x + 1 < width:
                value = min(value, float(distance[y, x + 1]) + 1.0)
            if y + 1 < height:
                value = min(value, float(distance[y + 1, x]) + 1.0)
                if x + 1 < width:
                    value = min(value, float(distance[y + 1, x + 1]) + diagonal)
                if x:
                    value = min(value, float(distance[y + 1, x - 1]) + diagonal)
            distance[y, x] = value
    return distance


def _normalized_points(indices: np.ndarray, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    return (
        (indices % width).astype(np.float32) / max(1, width - 1),
        (indices // width).astype(np.float32) / max(1, height - 1),
    )


def optimize_projection_alignment(
    source: np.ndarray,
    target: np.ndarray,
    *,
    pivot_x: float = 0.5,
    pivot_y: float = 0.5,
    lock_x: bool = False,
) -> tuple[ProjectionAlignment, dict[str, Any]]:
    height, width = source.shape
    if target.shape != source.shape:
        raise ValueError("projection alignment images must have matching dimensions")
    source_boundary = _boundary_indices(source)
    target_boundary = _boundary_indices(target)
    initial = ProjectionAlignment(pivot_x=pivot_x, pivot_y=pivot_y)
    diagnostic: dict[str, Any] = {
        "accepted": False,
        "raster_size": [width, height],
        "source_boundary_pixels": int(source_boundary.size),
        "target_boundary_pixels": int(target_boundary.size),
        "locked_longitudinal_x": bool(lock_x),
    }
    if not source_boundary.size or not target_boundary.size:
        diagnostic["reason"] = "empty geometry or target boundary"
        return initial, diagnostic

    distance_limit = max(6.0, min(width, height) * 0.08)
    source_distance = _distance_field(source_boundary, width, height, distance_limit)
    target_distance = _distance_field(target_boundary, width, height, distance_limit)
    source_x, source_y = _normalized_points(source_boundary, width, height)
    target_x, target_y = _normalized_points(target_boundary, width, height)

    def match_cost(alignment: ProjectionAlignment) -> float:
        transformed_x = alignment.pivot_x + alignment.offset_x + alignment.scale_x * (
            source_x - alignment.pivot_x
        )
        transformed_y = alignment.pivot_y + alignment.offset_y + alignment.scale_y * (
            source_y - alignment.pivot_y
        )
        valid = (
            (transformed_x >= 0.0)
            & (transformed_x <= 1.0)
            & (transformed_y >= 0.0)
            & (transformed_y <= 1.0)
        )
        source_cost = np.full(source_boundary.size, distance_limit, dtype=np.float32)
        if np.any(valid):
            px = np.rint(transformed_x[valid] * (width - 1)).astype(np.intp)
            py = np.rint(transformed_y[valid] * (height - 1)).astype(np.intp)
            source_cost[valid] = target_distance[py, px]

        inverse_x = alignment.pivot_x + (
            target_x - alignment.pivot_x - alignment.offset_x
        ) / alignment.scale_x
        inverse_y = alignment.pivot_y + (
            target_y - alignment.pivot_y - alignment.offset_y
        ) / alignment.scale_y
        valid = (
            (inverse_x >= 0.0)
            & (inverse_x <= 1.0)
            & (inverse_y >= 0.0)
            & (inverse_y <= 1.0)
        )
        target_cost = np.full(target_boundary.size, distance_limit, dtype=np.float32)
        if np.any(valid):
            px = np.rint(inverse_x[valid] * (width - 1)).astype(np.intp)
            py = np.rint(inverse_y[valid] * (height - 1)).astype(np.intp)
            target_cost[valid] = source_distance[py, px]
        return float(0.65 * source_cost.mean() + 0.35 * target_cost.mean())

    initial_cost = match_cost(initial)
    result = initial
    best_cost = initial_cost
    scale_step = 0.025
    offset_step = 0.015
    for _ in range(7):
        for parameter in range(4):
            if lock_x and parameter in (0, 2):
                continue
            best = result
            for direction in range(-2, 3):
                values = [result.scale_x, result.scale_y, result.offset_x, result.offset_y]
                values[parameter] += direction * (scale_step if parameter < 2 else offset_step)
                candidate = ProjectionAlignment(*values, result.pivot_x, result.pivot_y)
                if (
                    not SCALE_MINIMUM <= candidate.scale_x <= SCALE_MAXIMUM
                    or not SCALE_MINIMUM <= candidate.scale_y <= SCALE_MAXIMUM
                    or abs(candidate.offset_x) > OFFSET_LIMIT
                    or abs(candidate.offset_y) > OFFSET_LIMIT
                ):
                    continue
                candidate_cost = match_cost(candidate)
                if candidate_cost < best_cost:
                    best_cost = candidate_cost
                    best = candidate
            result = best
        scale_step *= 0.5
        offset_step *= 0.5

    improvement = initial_cost - best_cost
    diagnostic.update({
        "initial_cost": round(initial_cost, 6),
        "final_cost": round(best_cost, 6),
        "cost_improvement": round(improvement, 6),
    })
    if improvement < MINIMUM_COST_IMPROVEMENT:
        diagnostic["reason"] = "fit did not improve mask alignment enough"
        return initial, diagnostic
    diagnostic.update({
        "accepted": True,
        "scale": [result.scale_x, result.scale_y],
        "offset": [result.offset_x, result.offset_y],
        "pivot": [result.pivot_x, result.pivot_y],
    })
    return result, diagnostic


def _draw_triangles(image: np.ndarray, triangles: np.ndarray) -> None:
    try:
        import cv2
    except ImportError:
        canvas = Image.fromarray(image)
        painter = ImageDraw.Draw(canvas)
        for triangle in triangles:
            painter.polygon([tuple(map(float, point)) for point in triangle], fill=255)
        image[:] = np.asarray(canvas, dtype=np.uint8)
        return
    for start in range(0, len(triangles), 8192):
        cv2.fillPoly(image, triangles[start : start + 8192], 255, lineType=cv2.LINE_8)


def _geometry_raster(
    meshes: list[LocalProjectionMesh],
    geometry_side: int,
    axis: tuple[int, int, float, float],
    bounds: tuple[float, float, float, float],
    facing: np.ndarray,
    width: int,
    height: int,
) -> tuple[np.ndarray, int]:
    minimum_x, minimum_y, maximum_x, maximum_y = bounds
    axis_x, axis_y, scale_x, scale_y = axis
    axis_width = maximum_x - minimum_x
    axis_height = maximum_y - minimum_y
    image = np.zeros((height, width), dtype=np.uint8)
    triangle_count = 0
    for mesh in meshes:
        if not mesh.projection_sides & (1 << geometry_side):
            continue
        triangles = mesh.indices.reshape(-1, 3)
        valid = np.all((triangles >= 0) & (triangles < len(mesh.positions)), axis=1)
        triangles = triangles[valid]
        if not triangles.size:
            continue
        normals = mesh.normals[triangles]
        front_facing = np.sum(normals, axis=1).dot(facing) > 0.0
        triangles = triangles[front_facing]
        if not triangles.size:
            continue
        projected = np.empty((len(mesh.positions), 2), dtype=np.float32)
        projected[:, 0] = (
            (mesh.positions[:, axis_x] * scale_x - minimum_x) / axis_width * (width - 1)
        )
        projected[:, 1] = (
            (mesh.positions[:, axis_y] * scale_y - minimum_y) / axis_height * (height - 1)
        )
        polygons = np.rint(projected[triangles]).astype(np.int32)
        _draw_triangles(image, polygons)
        triangle_count += len(polygons)
    return image >= 128, triangle_count


def _target_raster(mask: np.ndarray, region: list[float], width: int, height: int) -> np.ndarray:
    x = (np.arange(width, dtype=np.float32) + 0.5) / width
    y = (np.arange(height, dtype=np.float32) + 0.5) / height
    mask_x = np.rint((region[0] + (region[1] - region[0]) * x) * (mask.shape[1] - 1))
    mask_y = np.rint((region[2] + (region[3] - region[2]) * y) * (mask.shape[0] - 1))
    mask_x = np.clip(mask_x.astype(np.intp), 0, mask.shape[1] - 1)
    mask_y = np.clip(mask_y.astype(np.intp), 0, mask.shape[0] - 1)
    return mask[np.ix_(mask_y, mask_x)] >= 128


def _longitudinal_pivot(assembly: dict[str, Any]) -> float | None:
    centers = assembly.get("wheel_centers") or {}
    samples = []
    for name in ("front_left", "front_right", "rear_left", "rear_right"):
        value = centers.get(name)
        if isinstance(value, list) and len(value) == 3 and math.isfinite(float(value[2])):
            samples.append(float(value[2]))
    if len(samples) < 2:
        return None
    front = max(samples)
    rear = min(samples)
    return (front + rear) * 0.5 if front - rear >= 0.5 else None


def build_aligned_projection_bounds(
    meshes: list[LocalProjectionMesh],
    sections: list[dict[str, Any]],
    masks: dict[int, np.ndarray],
    assembly: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    pivot_z = _longitudinal_pivot(assembly)
    locators = assembly.get("locators") or {}
    bumper_front = locators.get("bumper_front")
    bumper_rear = locators.get("bumper_rear")

    for section in sections:
        slot = int(section["slot_index"])
        geometry_side = SLOT_GEOMETRY_SIDES[slot]
        axis_values = section["projection_axis"]
        axis = (
            int(axis_values[0]),
            int(axis_values[1]),
            float(axis_values[2]),
            float(axis_values[3]),
        )
        candidates = [mesh for mesh in meshes if mesh.projection_sides & (1 << geometry_side)]
        if not candidates:
            continue
        axis_x, axis_y, scale_x, scale_y = axis
        minimum_x = min(float(np.min(mesh.positions[:, axis_x] * scale_x)) for mesh in candidates)
        maximum_x = max(float(np.max(mesh.positions[:, axis_x] * scale_x)) for mesh in candidates)
        minimum_y = min(float(np.min(mesh.positions[:, axis_y] * scale_y)) for mesh in candidates)
        maximum_y = max(float(np.max(mesh.positions[:, axis_y] * scale_y)) for mesh in candidates)
        lock_x = False
        if (
            slot in (2, 3, 4)
            and axis_x == 2
            and isinstance(bumper_front, list)
            and len(bumper_front) == 3
            and isinstance(bumper_rear, list)
            and len(bumper_rear) == 3
        ):
            first = float(bumper_front[2]) * scale_x
            second = float(bumper_rear[2]) * scale_x
            if math.isfinite(first) and math.isfinite(second) and abs(first - second) >= 0.5:
                minimum_x, maximum_x = sorted((first, second))
                lock_x = True
        if maximum_x <= minimum_x or maximum_y <= minimum_y:
            continue

        region = section["projection_mask_region"]
        region_width = abs(float(region[1]) - float(region[0])) * 2048.0
        region_height = abs(float(region[3]) - float(region[2])) * 1024.0
        if region_width < 1.0 or region_height < 1.0:
            continue
        raster_width = LONG_EDGE if region_width >= region_height else max(
            MIN_EDGE, round(LONG_EDGE * region_width / region_height)
        )
        raster_height = LONG_EDGE if region_height >= region_width else max(
            MIN_EDGE, round(LONG_EDGE * region_height / region_width)
        )
        bounds = (minimum_x, minimum_y, maximum_x, maximum_y)
        facing = np.asarray(section["facing"], dtype=np.float32)
        source, triangle_count = _geometry_raster(
            candidates,
            geometry_side,
            axis,
            bounds,
            facing,
            raster_width,
            raster_height,
        )
        target = _target_raster(masks[slot], region, raster_width, raster_height)
        pivot_x = 0.5
        pivot_y = 0.5
        if slot in (2, 3, 4) and pivot_z is not None:
            if axis_x == 2:
                pivot_x = (scale_x * pivot_z - minimum_x) / (maximum_x - minimum_x)
            if axis_y == 2:
                pivot_y = (scale_y * pivot_z - minimum_y) / (maximum_y - minimum_y)
        alignment, diagnostic = optimize_projection_alignment(
            source,
            target,
            pivot_x=pivot_x,
            pivot_y=pivot_y,
            lock_x=lock_x,
        )
        width = (maximum_x - minimum_x) / alignment.scale_x
        height = (maximum_y - minimum_y) / alignment.scale_y
        start_x = alignment.pivot_x + alignment.offset_x - alignment.scale_x * alignment.pivot_x
        start_y = alignment.pivot_y + alignment.offset_y - alignment.scale_y * alignment.pivot_y
        aligned_minimum_x = minimum_x - start_x * width
        aligned_minimum_y = minimum_y - start_y * height
        diagnostic["rasterized_triangles"] = triangle_count
        results[slot] = {
            "minimum": [aligned_minimum_x, aligned_minimum_y],
            "maximum": [aligned_minimum_x + width, aligned_minimum_y + height],
            "alignment": diagnostic,
        }
    return results
