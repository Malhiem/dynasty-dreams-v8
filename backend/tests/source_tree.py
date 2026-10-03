"""Read a frontend entry and its locally imported implementation components."""
import re
from pathlib import Path


def read_source(path, *args, include_imports=True, **kwargs):
    if not isinstance(path, (str, Path)) and not hasattr(path, "__fspath__"):
        return path.read_text(*args, **kwargs)
    entry = Path(path)
    if not include_imports:
        return entry.read_text(*args, **kwargs)
    if entry.suffix not in (".tsx", ".jsx", ".ts", ".js") or "frontend" not in entry.parts:
        return entry.read_text(*args, **kwargs)
    root = Path(*entry.parts[:entry.parts.index("frontend")+1]) / "src"
    seen = set()
    def visit(current):
        if current in seen:
            return ""
        seen.add(current)
        source = current.read_text(*args, **kwargs)
        children = []
        for target in re.findall(r"(?:from\s*|import\s*)[\"']([^\"']+)[\"']", source):
            if target.startswith("@/"):
                candidate = root / target[2:]
            elif target.startswith("."):
                candidate = current.parent / target
            else:
                continue
            choices = [candidate] + [Path(str(candidate)+ext) for ext in (".tsx", ".jsx", ".ts", ".js")] + [candidate / ("index"+ext) for ext in (".tsx", ".jsx", ".ts", ".js")]
            child = next((p.resolve() for p in choices if p.is_file() and p.suffix in (".tsx", ".jsx", ".ts", ".js")), None)
            if child and child.is_relative_to(root.resolve()):
                children.append(visit(child))
        return "\n".join([source, *children])
    return visit(entry.resolve())
