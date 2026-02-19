"""Scene state — central data model for the MVP."""

from dataclasses import dataclass


@dataclass
class TrackedObject:
    """One object on the canvas, tied to a QGraphicsItem."""
    name: str        # e.g. "eq_1", "eq_2"
    obj_type: str    # "mathtex" for now
    latex: str
    color: str       # hex, e.g. "#FFFFFF"


@dataclass
class AnimationEntry:
    """One animation step in the scene's animation list."""
    target_name: str   # name of the TrackedObject
    anim_type: str     # "FadeIn", "FadeOut", "Write", "ShowCreation"
    duration: float    # seconds
    easing: str        # "smooth", "linear", etc.


class SceneState:
    """Holds all state for the current scene. Single source of truth."""

    def __init__(self):
        self._objects: dict[str, TrackedObject] = {}
        self._items: dict[str, object] = {}  # name -> QGraphicsItem
        self._animations: list[AnimationEntry] = []
        self._name_counters: dict[str, int] = {}

    # --- Object tracking ---

    def next_name(self, prefix: str = "eq") -> str:
        count = self._name_counters.get(prefix, 0) + 1
        self._name_counters[prefix] = count
        return f"{prefix}_{count}"

    def register(self, name: str, tracked: TrackedObject, item: object) -> None:
        self._objects[name] = tracked
        self._items[name] = item

    def unregister(self, name: str) -> None:
        self._objects.pop(name, None)
        self._items.pop(name, None)
        self._animations = [a for a in self._animations if a.target_name != name]

    def get_tracked(self, name: str) -> TrackedObject | None:
        return self._objects.get(name)

    def get_item(self, name: str) -> object | None:
        return self._items.get(name)

    def find_name_for_item(self, item: object) -> str | None:
        for name, registered_item in self._items.items():
            if registered_item is item:
                return name
        return None

    def all_objects(self) -> list[tuple[str, TrackedObject]]:
        return list(self._objects.items())

    def object_names(self) -> list[str]:
        return list(self._objects.keys())

    # --- Animation list ---

    def add_animation(self, entry: AnimationEntry) -> None:
        self._animations.append(entry)

    def remove_animation(self, index: int) -> None:
        if 0 <= index < len(self._animations):
            self._animations.pop(index)

    def move_animation(self, index: int, delta: int) -> None:
        new_index = index + delta
        if 0 <= new_index < len(self._animations):
            self._animations[index], self._animations[new_index] = (
                self._animations[new_index], self._animations[index]
            )

    def all_animations(self) -> list[AnimationEntry]:
        return list(self._animations)
