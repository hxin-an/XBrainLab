from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dev.build_docs_portal import PortalBuildError, assemble_portal


def _write_site(root: Path, *, homepage_link: str, marker: str) -> None:
    (root / "assets/stylesheets").mkdir(parents=True)
    (root / "assets/javascripts/workers").mkdir(parents=True)
    (root / "search").mkdir(parents=True)
    (root / "assets/stylesheets/main.test.min.css").write_text(
        f"/* {marker} */", encoding="utf-8"
    )
    (root / "assets/javascripts/bundle.test.min.js").write_text(
        f"// {marker}", encoding="utf-8"
    )
    (root / "assets/javascripts/workers/search.test.min.js").write_text(
        f"// {marker}", encoding="utf-8"
    )
    (root / "search/search_index.json").write_text(
        json.dumps({"config": {}, "docs": [{"location": "", "title": marker}]}),
        encoding="utf-8",
    )
    (root / "index.html").write_text(
        "\n".join(
            (
                "<!doctype html>",
                '<link rel="stylesheet" href="assets/stylesheets/main.test.min.css">',
                '<script src="assets/javascripts/bundle.test.min.js"></script>',
                f'<a href="{homepage_link}">{marker}</a>',
            )
        ),
        encoding="utf-8",
    )


def test_assemble_portal_keeps_developer_root_and_isolates_user_assets(
    tmp_path: Path,
) -> None:
    developer = tmp_path / "developer"
    user = tmp_path / "user"
    output = tmp_path / "portal"
    _write_site(developer, homepage_link="guide/", marker="developer")
    _write_site(user, homepage_link="../", marker="user")
    (user / "404.html").write_text(
        '<link rel="icon" href="/assets/images/favicon.png">', encoding="utf-8"
    )
    output.mkdir()
    (output / "stale.txt").write_text("old artifact", encoding="utf-8")

    validation = assemble_portal(developer, user, output)

    assert "developer" in (output / "index.html").read_text(encoding="utf-8")
    assert "user" in (output / "guide/index.html").read_text(encoding="utf-8")
    assert "developer" in (output / "assets/stylesheets/main.test.min.css").read_text(
        encoding="utf-8"
    )
    assert "user" in (output / "guide/assets/stylesheets/main.test.min.css").read_text(
        encoding="utf-8"
    )
    assert not (output / "guide/404.html").exists()
    assert not (output / "stale.txt").exists()
    assert validation.html_pages == 2
    assert validation.search_documents == 2


def test_assemble_portal_rejects_reserved_route_without_replacing_output(
    tmp_path: Path,
) -> None:
    developer = tmp_path / "developer"
    user = tmp_path / "user"
    output = tmp_path / "portal"
    _write_site(developer, homepage_link="guide/", marker="developer")
    _write_site(user, homepage_link="../", marker="user")
    (developer / "guide").mkdir()
    output.mkdir()
    (output / "keep.txt").write_text("preserved", encoding="utf-8")

    with pytest.raises(PortalBuildError, match="already owns reserved route"):
        assemble_portal(developer, user, output)

    assert (output / "keep.txt").read_text(encoding="utf-8") == "preserved"


def test_assemble_portal_rejects_root_relative_user_asset_url(tmp_path: Path) -> None:
    developer = tmp_path / "developer"
    user = tmp_path / "user"
    output = tmp_path / "portal"
    _write_site(developer, homepage_link="guide/", marker="developer")
    _write_site(user, homepage_link="../", marker="user")
    with (user / "index.html").open("a", encoding="utf-8") as stream:
        stream.write('\n<img src="/assets/images/non-relocatable.png">\n')

    with pytest.raises(PortalBuildError, match="not path-relocatable"):
        assemble_portal(developer, user, output)

    assert not output.exists()
