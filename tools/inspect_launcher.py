"""Read PyInstaller code objects and compare with disk; never launch services."""
import argparse
import hashlib
import importlib.util
import marshal
from pathlib import Path
import sys
import types


def code_value(code):
    # PyInstaller rewrites co_filename. Keep bytecode, constants and line tables.
    return tuple(getattr(code, name) for name in (
        "co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
        "co_stacksize", "co_flags", "co_code", "co_names", "co_varnames",
        "co_freevars", "co_cellvars", "co_name", "co_qualname", "co_firstlineno",
        "co_linetable", "co_exceptiontable")) + (
        tuple(code_value(value) if isinstance(value, types.CodeType) else value for value in code.co_consts),)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-match", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    exe = root / "dist/PRPLauncher.exe"
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive("PYZ.pyz")
    if archive.extract("PYZ.pyz")[4:8] != importlib.util.MAGIC_NUMBER:
        raise SystemExit("Use the same Python minor version as the EXE build to inspect its bytecode.")
    modules = {name: pyz.extract(name) for name in pyz.toc
               if name.startswith(("launcher_", "services."))}
    modules["launcher_app"] = marshal.loads(archive.extract("launcher_app"))
    print("EXE:", exe)
    print("SHA256:", hashlib.sha256(exe.read_bytes()).hexdigest())
    print("Audit Python:", sys.executable)
    mismatches = []
    for name, code in sorted(modules.items()):
        path = root / "server" / (name.replace(".", "/") + ".py")
        matched = path.is_file() and code_value(code) == code_value(compile(path.read_bytes(), str(path), "exec", dont_inherit=True, optimize=0))
        print(("MATCH " if matched else "DIFFER ") + name)
        if not matched:
            mismatches.append(name)
    required = {"launcher_app", "launcher_core", "launcher_console", "launcher_imports",
                "services.role_config", "services.profile_config", "services.bridge_identity"}
    missing = required - modules.keys()
    if missing:
        print("MISSING:", ", ".join(sorted(missing)))
    print("AI bridge / phrase / motion business code is loaded by the external Python from disk.")
    if args.require_match and (mismatches or missing):
        raise SystemExit("Packaged launcher differs from current source; package verification failed.")
    print("Package/source comparison complete; this does not test real models or hardware.")


if __name__ == "__main__":
    main()
