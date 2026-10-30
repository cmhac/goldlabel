"""`goldlabel install`: copy the agent skills to where an agent reads them. Standard library only."""

import argparse
import os
import shutil
import sys
from importlib.resources import as_file, files
from pathlib import Path

from goldlabel._gold_rule import GOLD_RULE_FULL

# shortcut: four agents in a literal table, upgrade to an installer library when more are wanted.
# agent -> (skills folder, steering folder or None), under the project or the home directory.
AGENTS = {
    "claude": (".claude/skills", None),
    "codex": (".agents/skills", None),
    "copilot": (".agents/skills", None),
    "kiro": (".kiro/skills", ".kiro/steering"),
}

NEXT = {
    "claude": "restart Claude Code if the skills folder is new",
    "codex": "type $ or /skills to list them; restart Codex if they do not appear",
    "copilot": "run /skills reload in a session, then /skills list",
    "kiro": 'the default agent loads them; a custom agent must list "skill://{folder}/*/SKILL.md" in its resources',
}

POINTERS = """When working with the `goldlabel` library (content analysis over a corpus: candidates from seed phrases, keywords or the whole corpus, an LLM classifier checked against human-labelled gold data):

- Use the goldlabel agent skills: `goldlabel` (start here), then the one for the stage you are at: `goldlabel-connect`, `goldlabel-search-terms`, `goldlabel-taxonomy`, `goldlabel-candidates`, `goldlabel-tune`, `goldlabel-run`. If they are not installed, run `goldlabel install kiro`, or print the rule with `import goldlabel; print(goldlabel.GOLD_RULE_FULL)`.
- Never run a full classification without showing `clf.estimate(...)` (calls, cost, time) and getting a yes from the user.
- Never put API keys or database URLs in a notebook, script or file; they come from environment variables.
- Never evaluate the test split to guide edits, and never fold a spent test split into dev without the user's explicit yes.
"""


def steering_text() -> str:
    return f"---\ninclusion: always\n---\n\n{GOLD_RULE_FULL}\n{POINTERS}"


def _same(a: Path, b: Path) -> bool:
    def tree(root):
        return {
            p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
        }

    return tree(a) == tree(b)


def _put(src: Path, dest: Path) -> None:
    """Copy the folder `src` to `dest` through a temporary sibling, keeping the old one on failure."""
    tmp = dest.with_name(f".{dest.name}.tmp")
    old = dest.with_name(f".{dest.name}.old")
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("__pycache__"))
        if dest.exists():
            os.replace(dest, old)
        try:
            os.replace(tmp, dest)
        except BaseException:
            if old.exists():
                os.replace(old, dest)
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _put_file(text: str, dest: Path) -> None:
    tmp = dest.with_name(f".{dest.name}.tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def _show(path: Path, base: Path, home: Path) -> str:
    for root, prefix in ((base, ""), (home, "~/")):
        try:
            return prefix + path.relative_to(root).as_posix()
        except ValueError:
            pass
    return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="goldlabel", description="goldlabel agent skills")
    sub = ap.add_subparsers(dest="command", required=True)
    ins = sub.add_parser("install", help="install the agent skills for an agent")
    ins.add_argument("agents", nargs="*", help="claude, codex, copilot, kiro or all")
    ins.add_argument(
        "--global", dest="user", action="store_true", help="user-wide, not this project"
    )
    ins.add_argument(
        "--dir", help="write the skill folders to this directory (any other agent)"
    )
    ins.add_argument("--force", action="store_true", help="replace skills that differ")
    ins.add_argument(
        "--dry-run", action="store_true", help="print what would be written"
    )
    args = ap.parse_args(argv)
    valid = [*AGENTS, "all"]
    if args.dir and args.agents:
        ap.error("--dir takes no agent name")
    if not args.dir and not args.agents:
        ap.error(f"name an agent ({', '.join(valid)}) or give --dir")
    bad = [a for a in args.agents if a not in valid]
    if bad:
        print(f"unknown agent {', '.join(bad)}; choose from {', '.join(valid)}")
        return 1
    names = list(AGENTS) if "all" in args.agents else list(dict.fromkeys(args.agents))

    home, base = Path.home(), Path.home() if args.user else Path.cwd()
    targets: dict[Path, list[str]] = {}  # skills folder -> agents that read it
    steering: dict[Path, str] = {}
    if args.dir:
        targets[Path(args.dir).resolve()] = []
    for name in names:
        folder, steer = AGENTS[name]
        targets.setdefault(base / folder, []).append(name)
        if steer:
            steering[base / steer / "goldlabel.md"] = name

    code = 0
    with as_file(files("goldlabel") / "skills") as root:
        shipped = sorted(p for p in Path(root).iterdir() if p.is_dir())
        for folder, who in targets.items():
            if folder.is_symlink():
                print(f"refused    {_show(folder, base, home)}  is a symlink")
                code = 1
                continue
            if len(who) > 1:
                print(
                    f"shared     {_show(folder, base, home)}  {' and '.join(who)} read it"
                )
            for skill in shipped:
                dest, shown = (
                    folder / skill.name,
                    _show(folder / skill.name, base, home),
                )
                try:
                    if dest.exists() and _same(skill, dest):
                        status = "up to date"
                    elif dest.exists() and not args.force:
                        status, code = "differs (use --force to replace)", 1
                    elif args.dry_run:
                        status = "would write"
                    else:
                        status = "replaced" if dest.exists() else "written"
                        folder.mkdir(parents=True, exist_ok=True)
                        _put(skill, dest)
                except OSError as e:
                    status, code = f"failed: {e}", 1
                print(f"installed  {shown}  {status}")
        for dest, who in steering.items():
            shown = _show(dest, base, home)
            try:
                if dest.exists() and dest.read_text() == steering_text():
                    status = "up to date"
                elif dest.exists() and not args.force:
                    status, code = "differs (use --force to replace)", 1
                elif args.dry_run:
                    status = "would write"
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    _put_file(steering_text(), dest)
                    status = "written"
            except OSError as e:
                status, code = f"failed: {e}", 1
            print(f"installed  {shown}  {status}")
    for folder, who in targets.items():
        for name in who:
            shown = _show(folder, base, home)
            print(f"next ({name}): {NEXT[name].format(folder=shown)}")
    if args.dir:
        print(f"next: point your agent at {args.dir} (each folder there is one skill)")
    return code


if __name__ == "__main__":
    sys.exit(main())
