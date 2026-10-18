"""Load one source snapshot per release without replacing in-use module objects."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from threading import RLock

_LOCK = RLock()
# Internal dependencies precede agent. Keep this explicit when adding core modules.
_MODULES = (
    "storage",
    "evidence",
    "analytics",
    "prediction",
    "branding",
    "downloads",
    "agent",
)


def load_release(root):
    """Reuse identical code; changed source gets an isolated, complete package.

    Streamlit can rerun app.py while Python retains an earlier imported package.
    A private, content-derived name avoids mixing those releases. Compile the
    captured bytes directly so timestamp-valid older bytecode cannot be reused.
    Existing sessions and unrelated modules keep their own references.
    """
    root = Path(root).resolve()
    core = root / "creaseiq_core"
    paths = {path.stem: path for path in core.glob("*.py")}
    expected = {"__init__", *_MODULES}
    if set(paths) != expected:
        raise RuntimeError("The core module list does not match the release loader.")
    sources = {name: path.read_bytes() for name, path in paths.items()}
    fingerprint = sha256(str(root).encode())
    for name, content in sorted(sources.items()):
        fingerprint.update(name.encode() + b"\0" + content + b"\0")
    namespace = "_creaseiq_release_" + fingerprint.hexdigest()
    with _LOCK:
        ready = sys.modules.get(namespace)
        if ready is not None and getattr(ready, "release_ready", False):
            return ready
        created = []
        try:
            spec = spec_from_file_location(
                namespace, paths["__init__"], submodule_search_locations=[str(core)]
            )
            package = module_from_spec(spec)
            sys.modules[namespace] = package
            created.append(namespace)
            exec(
                compile(sources["__init__"], str(paths["__init__"]), "exec"),
                package.__dict__,
            )
            for name in _MODULES:
                qualified = namespace + "." + name
                spec = spec_from_file_location(qualified, paths[name])
                module = module_from_spec(spec)
                sys.modules[qualified] = module
                created.append(qualified)
                exec(compile(sources[name], str(paths[name]), "exec"), module.__dict__)
                setattr(package, name, module)
            package.release_fingerprint = fingerprint.hexdigest()
            package.release_ready = True
            return package
        except BaseException:
            for name in reversed(created):
                sys.modules.pop(name, None)
            raise
