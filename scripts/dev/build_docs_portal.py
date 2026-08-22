"""Build and validate the combined GitHub Pages documentation artifact."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build/dev-artifacts/docs-portal-review"
DEVELOPER_CONFIG = ROOT / "mkdocs.yml"
USER_CONFIG = ROOT / "mkdocs.user.yml"
GUIDE_SUBPATH = Path("guide")
PAGES_BASE_PATH = "/XBrainLab/"


class PortalBuildError(RuntimeError):
    """Raised when the two sites cannot form one relocatable Pages artifact."""


@dataclass(frozen=True)
class PortalValidation:
    html_pages: int
    local_references: int
    search_documents: int


class _ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        self._collect(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        self._collect(attrs)

    def _collect(self, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.references.append(value)


def _references(path: Path) -> list[str]:
    parser = _ReferenceParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.references


def _resolve_local_target(
    page: Path,
    reference: str,
    portal_root: Path,
    *,
    require_relocatable: bool,
) -> Path | None:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    if parsed.path.startswith("/"):
        if require_relocatable:
            raise PortalBuildError(
                f"root-relative URL is not path-relocatable: {page}: {reference}"
            )
        if not parsed.path.startswith(PAGES_BASE_PATH):
            raise PortalBuildError(
                f"developer URL is outside the configured Pages base: {page}: {reference}"
            )
        relative_path = unquote(parsed.path.removeprefix(PAGES_BASE_PATH))
        target = (portal_root / relative_path).resolve()
    else:
        target = (page.parent / unquote(parsed.path)).resolve()
    portal = portal_root.resolve()
    if not target.is_relative_to(portal):
        raise PortalBuildError(
            f"local URL escapes the Pages artifact: {page}: {reference}"
        )
    if target.is_dir():
        target = target / "index.html"
    elif not target.exists() and not target.suffix:
        html_target = target.with_suffix(".html")
        if html_target.is_file():
            target = html_target
    return target


def _require_material_assets(site_root: Path) -> None:
    required_patterns = (
        "assets/stylesheets/main.*.min.css",
        "assets/javascripts/bundle.*.min.js",
        "assets/javascripts/workers/search.*.min.js",
        "search/search_index.json",
    )
    for pattern in required_patterns:
        if not any(site_root.glob(pattern)):
            raise PortalBuildError(
                f"built site is missing required Material/search asset: "
                f"{site_root}/{pattern}"
            )


def _validate_search_index(site_root: Path) -> int:
    index_path = site_root / "search/search_index.json"
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortalBuildError(f"invalid search index {index_path}: {exc}") from exc

    documents = payload.get("docs")
    if not isinstance(documents, list):
        raise PortalBuildError(f"search index has no docs list: {index_path}")

    for document in documents:
        if not isinstance(document, dict) or not isinstance(
            document.get("location"), str
        ):
            raise PortalBuildError(
                f"search index has an invalid document: {index_path}"
            )
        location = document["location"]
        parsed = urlsplit(location)
        if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
            raise PortalBuildError(
                f"search location is not path-relocatable: {index_path}: {location}"
            )
        target = (site_root / unquote(parsed.path)).resolve()
        if not target.is_relative_to(site_root.resolve()):
            raise PortalBuildError(
                f"search location escapes its site root: {index_path}: {location}"
            )
        if target.is_dir():
            target = target / "index.html"
        elif not target.exists() and not target.suffix:
            target = target.with_suffix(".html")
        if not target.is_file():
            raise PortalBuildError(
                f"search location has no built page: {index_path}: {location}"
            )
    return len(documents)


def validate_portal(
    portal_root: Path, guide_subpath: Path = GUIDE_SUBPATH
) -> PortalValidation:
    portal_root = portal_root.resolve()
    guide_root = portal_root / guide_subpath
    developer_index = portal_root / "index.html"
    developer_testing = portal_root / "developer/testing/index.html"
    user_index = guide_root / "index.html"

    for index in (developer_index, user_index):
        if not index.is_file():
            raise PortalBuildError(f"missing portal entry page: {index}")
    if not developer_testing.is_file():
        raise PortalBuildError(f"missing developer testing guide: {developer_testing}")

    _require_material_assets(portal_root)
    _require_material_assets(guide_root)

    developer_refs = _references(developer_index)
    user_refs = _references(user_index)
    if f"{guide_subpath.as_posix()}/" not in developer_refs:
        raise PortalBuildError("developer homepage does not link to the user guide")
    if "developer/testing/" not in developer_refs:
        raise PortalBuildError(
            "developer homepage does not link to the developer testing guide"
        )
    if "../" not in user_refs:
        raise PortalBuildError("user guide homepage does not link to engineering docs")

    html_pages = sorted(portal_root.rglob("*.html"))
    local_references = 0
    for page in html_pages:
        for reference in _references(page):
            target = _resolve_local_target(
                page,
                reference,
                portal_root,
                require_relocatable=page.is_relative_to(guide_root),
            )
            if target is None:
                continue
            local_references += 1
            if not target.is_file():
                relative_page = page.relative_to(portal_root)
                raise PortalBuildError(
                    f"broken local URL in {relative_page}: {reference}"
                )

    search_documents = _validate_search_index(portal_root)
    search_documents += _validate_search_index(guide_root)
    return PortalValidation(
        html_pages=len(html_pages),
        local_references=local_references,
        search_documents=search_documents,
    )


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _replace_directory(staged: Path, destination: Path) -> None:
    backup = staged.parent / "previous-portal"
    if destination.exists() or destination.is_symlink():
        destination.replace(backup)
    try:
        staged.replace(destination)
    except Exception:
        if backup.exists() or backup.is_symlink():
            backup.replace(destination)
        raise
    _remove_path(backup)


def assemble_portal(
    developer_site: Path,
    user_site: Path,
    output_dir: Path,
    guide_subpath: Path = GUIDE_SUBPATH,
) -> PortalValidation:
    developer_site = developer_site.resolve()
    user_site = user_site.resolve()
    output_dir = output_dir.resolve()

    if guide_subpath.is_absolute() or ".." in guide_subpath.parts:
        raise PortalBuildError(f"invalid user-guide subpath: {guide_subpath}")
    for site in (developer_site, user_site):
        if not (site / "index.html").is_file():
            raise PortalBuildError(f"MkDocs build has no index.html: {site}")
    if (developer_site / guide_subpath).exists():
        raise PortalBuildError(
            f"developer build already owns reserved route: /{guide_subpath.as_posix()}/"
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".docs-portal-assembly-", dir=output_dir.parent
    ) as temporary:
        staged = Path(temporary) / "portal"
        shutil.copytree(developer_site, staged)
        shutil.copytree(user_site, staged / guide_subpath)
        # A nested MkDocs 404 assumes a domain root and cannot serve /guide/ URLs.
        (staged / guide_subpath / "404.html").unlink(missing_ok=True)
        validation = validate_portal(staged, guide_subpath)
        _replace_directory(staged, output_dir)
    return validation


def _build_mkdocs(config: Path, site_dir: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "mkdocs",
        "build",
        "--strict",
        "--config-file",
        str(config),
        "--site-dir",
        str(site_dir),
    ]
    subprocess.run(command, cwd=ROOT, check=True)  # noqa: S603 - fixed executable


def build_docs_portal(output_dir: Path = DEFAULT_OUTPUT) -> PortalValidation:
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".docs-portal-build-", dir=output_dir.parent
    ) as temporary:
        build_root = Path(temporary)
        developer_site = build_root / "developer"
        user_site = build_root / "user"
        _build_mkdocs(DEVELOPER_CONFIG, developer_site)
        _build_mkdocs(USER_CONFIG, user_site)
        return assemble_portal(developer_site, user_site, output_dir)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build developer docs at / and the user guide at /guide/."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"combined artifact directory (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        validation = build_docs_portal(args.output_dir)
    except (PortalBuildError, subprocess.CalledProcessError) as exc:
        print(f"docs portal build failed: {exc}", file=sys.stderr)
        return 1

    output = args.output_dir.resolve()
    try:
        output_label = output.relative_to(ROOT)
    except ValueError:
        output_label = output
    print(f"Docs portal: {output_label}")
    print("Routes: developer=/ user-guide=/guide/")
    print(
        "Validated: "
        f"{validation.html_pages} HTML pages, "
        f"{validation.local_references} local references, "
        f"{validation.search_documents} search documents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
