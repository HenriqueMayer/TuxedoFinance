"""Project configuration: settings, URL routes, the API mount and shared helpers."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tuxedo-finance")
except PackageNotFoundError:  # The project is not installed as a package.
    import tomllib
    from pathlib import Path

    with (Path(__file__).resolve().parent.parent / "pyproject.toml").open("rb") as manifest:
        __version__ = tomllib.load(manifest)["project"]["version"]
