"""Load repository-local agents without mixing cached module generations."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from threading import RLock

_LOCK = RLock()
_FUNCTIONS = (
    "generate_player_scout_report", "scout_context_fingerprint",
    "generate_matchup_report", "matchup_context_fingerprint",
    "generate_auction_report", "auction_context_fingerprint",
)


class AgentRuntimeError(RuntimeError):
    """The local agent release cannot currently be loaded."""


def load_agents(root):
    """Capture, compile and cache one complete agent source version.

    The private namespace bypasses unrelated or older sys.modules['agents']
    entries. Compiling captured bytes avoids timestamp-valid stale bytecode.
    Existing callers keep their original module objects during an update.
    """
    path = Path(root).resolve() / "agents.py"
    try:
        source = path.read_bytes()
    except OSError:
        raise AgentRuntimeError("The local agent source is unavailable.") from None
    version = sha256(str(path).encode() + b"\0" + source).hexdigest()
    name = "_ipl360_agents_" + version
    with _LOCK:
        existing = sys.modules.get(name)
        if existing is not None and getattr(existing, "_release_ready", False):
            return existing
        try:
            spec = spec_from_file_location(name, path)
            module = module_from_spec(spec)
            sys.modules[name] = module
            exec(compile(source, str(path), "exec"), module.__dict__)
            error_type = getattr(module, "ScoutReportError", None)
            if not isinstance(error_type, type) or not issubclass(error_type, Exception):
                raise AgentRuntimeError("The local agent error contract is incomplete.")
            if any(not callable(getattr(module, field, None)) for field in _FUNCTIONS):
                raise AgentRuntimeError("The local agent release is missing required functions.")
            module._release_ready = True
            return module
        except Exception:
            sys.modules.pop(name, None)
            raise AgentRuntimeError("The local agent release could not be loaded completely.") from None
