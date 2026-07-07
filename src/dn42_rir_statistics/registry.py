from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DATA_DIRECTORIES = ("aut-num", "inetnum", "inet6num")


@dataclass(frozen=True)
class RegistryObject:
    object_type: str
    path: Path
    attributes: dict[str, list[str]]

    def first(self, key: str, default: str = "") -> str:
        values = self.attributes.get(key.lower())
        if not values:
            return default
        return values[0]

    def all(self, key: str) -> list[str]:
        return self.attributes.get(key.lower(), [])


def parse_object_file(path: Path) -> dict[str, list[str]]:
    attributes: dict[str, list[str]] = {}
    current_key: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue

            if line[:1].isspace() and current_key:
                value = line.strip()
                if value:
                    attributes[current_key][-1] = f"{attributes[current_key][-1]} {value}"
                continue

            if ":" not in line:
                current_key = None
                continue

            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if not key:
                current_key = None
                continue

            attributes.setdefault(key, []).append(value)
            current_key = key

    return attributes


def registry_data_dir(registry_root: Path) -> Path:
    data_dir = registry_root / "data"
    if data_dir.is_dir():
        return data_dir
    return registry_root


def load_registry_names(registry_root: Path) -> set[str]:
    data_dir = registry_data_dir(registry_root)
    registry_dir = data_dir / "registry"
    names: set[str] = set()

    if not registry_dir.is_dir():
        return names

    for path in sorted(registry_dir.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        attributes = parse_object_file(path)
        registry_name = attributes.get("registry", [path.name])[0]
        if registry_name:
            names.add(registry_name.strip().lower())

    return names


def iter_registry_objects(registry_root: Path) -> list[RegistryObject]:
    data_dir = registry_data_dir(registry_root)
    objects: list[RegistryObject] = []

    for object_type in DATA_DIRECTORIES:
        object_dir = data_dir / object_type
        if not object_dir.is_dir():
            continue
        for path in sorted(object_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            objects.append(
                RegistryObject(
                    object_type=object_type,
                    path=path,
                    attributes=parse_object_file(path),
                )
            )

    return objects
