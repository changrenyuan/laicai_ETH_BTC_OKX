from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    "logs",
    "data",
    ".git"
}

OUTPUT = ROOT / "snapshot_all_code.py"
TREE = ROOT / "snapshot_tree.txt"

def collect_py_files():
    files = []
    for p in ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)

def write_code_snapshot(files):
    with OUTPUT.open("w", encoding="utf-8") as out:
        for f in files:
            out.write(f"\n\n# {'=' * 80}\n")
            out.write(f"# FILE: {f.relative_to(ROOT)}\n")
            out.write(f"# {'=' * 80}\n\n")
            out.write(f.read_text(encoding="utf-8", errors="ignore"))

def write_tree(files):
    with TREE.open("w", encoding="utf-8") as out:
        for f in files:
            out.write(str(f.relative_to(ROOT)) + "\n")

if __name__ == "__main__":
    py_files = collect_py_files()
    write_code_snapshot(py_files)
    write_tree(py_files)
    print(f"✅ Snapshot done: {len(py_files)} files")
