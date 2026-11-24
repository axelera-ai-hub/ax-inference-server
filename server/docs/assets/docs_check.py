#!/usr/bin/env python3
"""Check and maintain the markdown documentation under server/docs and client/docs.

The script verifies relative links, flags long sentences, checks that each reference area
index lists every page, and writes line ranges next to `path::Symbol` source citations.

Note:
    Pages cite code as `path::Symbol`. The `lines` command appends ` (lines A-B)` after the
    citation. Run it after code changes. `lines --check` fails when a range is out of date.
"""
import argparse
import ast
import os
import re
import sys

ROOTS = ("server/docs", "client/docs")
SKIP_DIRS = ("client/docs/helper", ".trash")
MAX_WORDS = 25
CITE_RE = re.compile(
    r"`(?P<path>[\w./-]+\.(?:py|cpp|h|hpp|sh|proto|js|mjs))::(?P<sym>[\w.:~]+)`"
    r"(?P<rng> \(lines \d+-\d+\))?"
)
LINK_RE = re.compile(r"\]\(([^)#\s]+)")
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)


def repo_root():
    """Return the repository root, found by walking up from this file.

    Returns:
        str: Absolute path of the directory that contains `server/docs`.

    Raises:
        RuntimeError: If no ancestor directory contains `server/docs`.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    while here != os.path.dirname(here):
        if os.path.isdir(os.path.join(here, "server", "docs")):
            return here
        here = os.path.dirname(here)
    raise RuntimeError("repository root not found")


def markdown_files(root):
    """List the markdown files of the documentation trees.

    Args:
        root (str): Repository root.

    Returns:
        list[str]: Sorted repo-relative paths. Helper agent docs and `.trash` are skipped.
    """
    found = []
    for base in ROOTS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, base)):
            rel = os.path.relpath(dirpath, root)
            if any(s in rel.split(os.sep) or rel.startswith(s) for s in SKIP_DIRS):
                dirnames[:] = []
                continue
            found += [os.path.join(rel, f) for f in filenames if f.endswith(".md")]
    return sorted(found)


def check_links(root, files):
    """Report relative links and index entries that do not resolve.

    Args:
        root (str): Repository root.
        files (list[str]): Repo-relative markdown paths.

    Returns:
        list[str]: One message per broken link.
    """
    problems = []
    for rel in files:
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        for link in LINK_RE.findall(text):
            if re.match(r"^[a-z]+:", link):
                continue
            target = os.path.normpath(os.path.join(root, os.path.dirname(rel), link))
            if not os.path.exists(target):
                problems.append(f"{rel}: broken link {link}")
    return problems


def check_sentences(root, files):
    """Report prose sentences longer than the word limit.

    Args:
        root (str): Repository root.
        files (list[str]): Repo-relative markdown paths.

    Returns:
        list[str]: One message per long sentence. Code fences and table rows are ignored.
    """
    problems = []
    for rel in files:
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        body = CODE_FENCE_RE.sub("", text)
        for sentence in re.split(r"(?<=[.!?])\s+|\n", body):
            if sentence.lstrip().startswith("|"):
                continue
            if len(sentence.split()) > MAX_WORDS:
                problems.append(f"{rel}: {len(sentence.split())} words: {sentence.strip()[:70]}")
    return problems


def check_indexes(root):
    """Check that each reference area index lists every page of the area, and nothing else.

    Args:
        root (str): Repository root.

    Returns:
        list[str]: One message per missing or dangling index entry.
    """
    problems = []
    for base in ROOTS:
        ref = os.path.join(root, base, "reference")
        if not os.path.isdir(ref):
            continue
        for area in sorted(os.listdir(ref)):
            area_dir = os.path.join(ref, area)
            if not os.path.isdir(area_dir):
                continue
            pages = set()
            for dirpath, _, filenames in os.walk(area_dir):
                for name in filenames:
                    if name.endswith(".md"):
                        pages.add(os.path.relpath(os.path.join(dirpath, name), area_dir))
            pages.discard("index.md")
            index = os.path.join(area_dir, "index.md")
            if not os.path.exists(index):
                problems.append(f"{os.path.relpath(area_dir, root)}: index.md missing")
                continue
            linked = {
                os.path.normpath(link)
                for link in LINK_RE.findall(open(index, encoding="utf-8").read())
                if link.endswith(".md") and os.path.exists(os.path.join(area_dir, link))
                and os.path.commonpath([area_dir, os.path.normpath(os.path.join(area_dir, link))]) == area_dir
            }
            for name in sorted(pages - linked):
                problems.append(f"{os.path.relpath(index, root)}: page not listed: {name}")
    return problems


def python_range(source, symbol):
    """Find the line range of a Python class, function or method.

    Args:
        source (str): File contents.
        symbol (str): Dotted name such as `Class.method`.

    Returns:
        tuple[int, int] | None: First and last line, or None when the symbol is absent.
    """
    node = ast.parse(source)
    for part in symbol.split("."):
        nxt = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == part:
                nxt = child
                break
            if isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                names = []
                for target in targets:
                    names += [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]
                if part in names:
                    nxt = child
                    break
        if nxt is None:
            return None
        node = nxt
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return start, node.end_lineno


def brace_range(lines, start):
    """Extend a definition that starts at `start` to its closing brace.

    Args:
        lines (list[str]): Source lines.
        start (int): Zero-based index of the first line.

    Returns:
        int: One-based line number of the last line of the block.
    """
    depth, seen = 0, False
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth, seen = depth + 1, True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return i + 1
        if not seen and lines[i].rstrip().endswith(";"):
            return i + 1
    return len(lines)


def generic_range(source, symbol, suffix):
    """Find the line range of a symbol in C++, proto, shell or JavaScript by name.

    Args:
        source (str): File contents.
        symbol (str): Name such as `Class::method`, `Message` or `function`.
        suffix (str): File extension without the dot.

    Returns:
        tuple[int, int] | None: First and last line, or None when no definition matches.
    """
    lines = source.splitlines()
    names = [n for n in re.split(r"::|\.", symbol) if n]
    last = re.escape(names[-1].lstrip("~"))
    patterns = [
        rf"^\s*(?:message|enum(?:\s+class)?|service|class|struct)\s+{last}\b",
        rf"^\s*(?:function\s+)?{last}\s*\(\)\s*\{{",
        rf"\b{re.escape('::'.join(names[-2:]))}\s*\(" if len(names) > 1 else None,
        rf"^[^/#\n]*\b{last}\s*\([^;]*$",
        rf"^[^/#\n]*\b{last}\s*\(.*\)\s*(?:const)?\s*(?:override)?\s*\{{",
        rf"^[^/#\n]*\b{last}\s*\(.*\)\s*(?:const)?\s*(?:override)?\s*;",
        rf"^\s*(?:using|typedef)\b.*\b{last}\b",
        rf"^\s*[\w:<>,\s*&]+\b{last}\s*(?:=|;)",
    ]
    for pat in filter(None, patterns):
        for i, line in enumerate(lines):
            if line.lstrip().startswith(("*", "//", "/*", "#")) and suffix != "sh":
                continue
            if re.search(pat, line):
                if suffix == "sh" and "{" not in line and "()" not in line:
                    continue
                return i + 1, (brace_range(lines, i) if suffix != "py" else i + 1)
    return None


def symbol_range(root, path, symbol):
    """Resolve a `path::Symbol` citation to a line range.

    Args:
        root (str): Repository root.
        path (str): Repo-relative source path.
        symbol (str): Symbol name.

    Returns:
        tuple[int, int] | None: First and last line, or None when the file or symbol is absent.
    """
    full = os.path.join(root, path)
    if not os.path.isfile(full):
        return None
    source = open(full, encoding="utf-8", errors="replace").read()
    if path.endswith(".py"):
        try:
            return python_range(source, symbol)
        except SyntaxError:
            return None
    return generic_range(source, symbol, path.rsplit(".", 1)[-1])


def update_citations(root, files, write):
    """Append or refresh the line range after every `path::Symbol` citation.

    Args:
        root (str): Repository root.
        files (list[str]): Repo-relative markdown paths.
        write (bool): Rewrite the files when True. Only report when False.

    Returns:
        list[str]: One message per citation that is stale, unresolved or missing a range.
    """
    problems = []
    for rel in files:
        full = os.path.join(root, rel)
        text = open(full, encoding="utf-8").read()

        def repl(match):
            found = symbol_range(root, match["path"], match["sym"])
            cite = f"`{match['path']}::{match['sym']}`"
            if found is None:
                problems.append(f"{rel}: unresolved {match['path']}::{match['sym']}")
                return match.group(0)
            new = f"{cite} (lines {found[0]}-{found[1]})"
            if new != match.group(0):
                problems.append(f"{rel}: range out of date for {match['path']}::{match['sym']}")
            return new

        updated = CITE_RE.sub(repl, text)
        if write and updated != text:
            open(full, "w", encoding="utf-8").write(updated)
    return problems


def main():
    """Run the selected checks and exit with status 1 when any problem is found."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["all", "links", "sentences", "index", "lines"])
    parser.add_argument("--write", action="store_true", help="With `lines`, rewrite the line ranges.")
    args = parser.parse_args()
    root = repo_root()
    files = markdown_files(root)
    problems = []
    if args.command in ("all", "links"):
        problems += check_links(root, files)
    if args.command in ("all", "sentences"):
        problems += check_sentences(root, files)
    if args.command in ("all", "index"):
        problems += check_indexes(root)
    if args.command in ("all", "lines") or (args.command == "lines" and args.write):
        problems += update_citations(root, files, args.write and args.command == "lines")
    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s) in {len(files)} file(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
