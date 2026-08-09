"""Headless recipe registry."""

from __future__ import annotations

from datalab.recipes import RecipeDescriptor

RECIPES: tuple[RecipeDescriptor, ...] = ()

__all__ = ["RECIPES"]
