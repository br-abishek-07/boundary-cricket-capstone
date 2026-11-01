"""Load a coherent repository-local data layer during Streamlit warm reruns."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from threading import RLock
from types import ModuleType

_LOCK = RLock()
_LOADER_FUNCTIONS = (
    "load_auction", "load_match_players", "load_matches", "load_player_registry",
    "load_squads", "load_deliveries", "load_clean_auction",
    "load_auction_player_links", "load_season_impact", "load_ipl_wickets", "load_ipl_rosters",
)
_METRIC_FUNCTIONS = (
    "phase_batting_metrics", "latest_auction_impact", "append_phase_evidence",
    "append_impact_evidence", "aggregate_season_impact",
)


class DataRuntimeError(RuntimeError):
    """The repository data modules are unavailable or incomplete."""


def load_data_layer(root):
    """Capture both sources and cache a complete release in a private package.

    Generic 'data_loader' and 'moneyball' modules may survive a hosted rerun or
    belong to another package. They are never reused or replaced. Both local
    sources are compiled from captured bytes, bypassing stale timestamp-based
    bytecode. Package-relative imports keep the loader's aggregation dependency
    in the same release. Existing callers retain their original module objects.
    """
    root = Path(root).resolve()
    try:
        sources = {name: (root / f"{name}.py").read_bytes()
                   for name in ("moneyball", "data_loader")}
    except OSError:
        raise DataRuntimeError("The repository data source is unavailable.") from None
    digest = sha256(str(root).encode())
    for name, source in sources.items():
        digest.update(b"\0" + name.encode() + b"\0" + source)
    package_name = "_ipl360_data_" + digest.hexdigest()
    with _LOCK:
        existing = sys.modules.get(package_name)
        if existing is not None and getattr(existing, "_release_ready", False):
            return existing
        names = [package_name, *(f"{package_name}.{name}" for name in sources)]
        try:
            package = ModuleType(package_name)
            package.__package__ = package_name
            package.__path__ = [str(root)]
            sys.modules[package_name] = package
            for name, source in sources.items():
                full_name = f"{package_name}.{name}"
                path = root / f"{name}.py"
                module = module_from_spec(spec_from_file_location(full_name, path))
                sys.modules[full_name] = module
                exec(compile(source, str(path), "exec"), module.__dict__)
                setattr(package, name, module)
            for module, required in [(package.data_loader, _LOADER_FUNCTIONS),
                                     (package.moneyball, _METRIC_FUNCTIONS)]:
                if any(not callable(getattr(module, name, None)) for name in required):
                    raise DataRuntimeError("The repository data release is incomplete.")
            package._release_ready = True
            return package
        except Exception:
            for name in reversed(names):
                sys.modules.pop(name, None)
            raise DataRuntimeError("The repository data release could not be loaded completely.") from None
