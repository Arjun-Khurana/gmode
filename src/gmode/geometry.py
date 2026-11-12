"""2D cross-section structures. Coordinates are in microns, x horizontal, y vertical."""
from typing import Annotated, Literal, Union

import numpy as np
from pydantic import BaseModel, Field, field_validator


class Rectangle(BaseModel):
    type: Literal["rectangle"] = "rectangle"
    name: str = "rectangle"
    material: str
    center: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float]

    def contains(self, x, y):
        (cx, cy), (w, h) = self.center, self.size
        return (np.abs(x - cx) <= w / 2) & (np.abs(y - cy) <= h / 2)

    def bounds(self):
        (cx, cy), (w, h) = self.center, self.size
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


class Circle(BaseModel):
    type: Literal["circle"] = "circle"
    name: str = "circle"
    material: str
    center: tuple[float, float] = (0.0, 0.0)
    radius: float

    def contains(self, x, y):
        cx, cy = self.center
        return (x - cx) ** 2 + (y - cy) ** 2 <= self.radius**2

    def bounds(self):
        (cx, cy), r = self.center, self.radius
        return cx - r, cy - r, cx + r, cy + r


class Polygon(BaseModel):
    type: Literal["polygon"] = "polygon"
    name: str = "polygon"
    material: str
    vertices: list[tuple[float, float]]

    @field_validator("vertices")
    @classmethod
    def _at_least_three(cls, v):
        if len(v) < 3:
            raise ValueError("a polygon needs at least 3 vertices")
        return v

    def contains(self, x, y):
        # even-odd ray casting, vectorized over points
        x, y = np.broadcast_arrays(x, y)
        inside = np.zeros(x.shape, dtype=bool)
        v = np.asarray(self.vertices)
        for (x1, y1), (x2, y2) in zip(v, np.roll(v, -1, axis=0)):
            if y1 == y2:
                continue
            crosses = (y1 > y) != (y2 > y)
            x_int = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            inside ^= crosses & (x < x_int)
        return inside

    def bounds(self):
        v = np.asarray(self.vertices)
        return *v.min(axis=0), *v.max(axis=0)

    @classmethod
    def trapezoid(cls, material: str, center: tuple[float, float], top_width: float, height: float,
                  sidewall_angle: float, name: str = "trapezoid") -> "Polygon":
        """Etched ridge with sidewalls `sidewall_angle` degrees from vertical (positive widens the base)."""
        cx, cy = center
        dw = height * np.tan(np.radians(sidewall_angle))
        b, t = cy - height / 2, cy + height / 2
        verts = [(cx - top_width / 2 - dw, b), (cx + top_width / 2 + dw, b),
                 (cx + top_width / 2, t), (cx - top_width / 2, t)]
        return cls(name=name, material=material, vertices=verts)


Structure = Annotated[Union[Rectangle, Circle, Polygon], Field(discriminator="type")]
