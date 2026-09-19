"""pip で配る形(pyproject.toml)の約束事。"""
import re
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = pytest.importorskip("tomli")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
PYPROJECT = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["README.md", "LICENSE", "THIRD_PARTY_LICENSES.md"])
def test_copies_match_the_repository_root(name):
    """setuptools はプロジェクトの外を読めないので複製を置いている。直下のものを直したら複製も直す。"""
    assert (PROJECT_ROOT / name).read_bytes() == (REPO_ROOT / name).read_bytes()


def test_runtime_dependencies_are_ranges_not_pins():
    """固定すると、利用者の環境のほかのソフトとぶつかって入らない。固定版は requirements.txt(exe と CI 用)。"""
    pinned = [dep for dep in PYPROJECT["project"]["dependencies"] if "==" in dep]

    assert pinned == []


def test_the_command_does_not_open_a_console():
    assert "graphica" in PYPROJECT["project"]["gui-scripts"]
    assert "graphica" not in PYPROJECT["project"].get("scripts", {})


def test_every_subpackage_is_listed():
    """packages は明示の列挙なので、足し忘れたパッケージは pip で入れた版から黙って抜け落ちる。"""
    package_root = PROJECT_ROOT / "graphica"
    on_disk = {
        ".".join(init.parent.relative_to(PROJECT_ROOT).parts)
        for init in package_root.rglob("__init__.py")
        if "__pycache__" not in init.parts and "plugins" not in init.relative_to(package_root).parts
    }

    assert on_disk - set(PYPROJECT["tool"]["setuptools"]["packages"]) == set()


def test_bundled_mit_icons_carry_their_notice():
    """MIT は複製に著作権表示と許諾文を含めることを求める。同梱の Tabler Icons の分を配布物に入れる。"""
    text = (PROJECT_ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")

    assert "Copyright (c) 2020-2026 Paweł Kuna" in text
    assert "The above copyright notice and this permission notice shall be included in all" in text


def test_readme_links_work_on_pypi():
    """PyPI は README をリポジトリの外で表示するので、相対リンクは切れる。"""
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", text)

    assert [t for t in targets if not t.startswith(("https://", "http://", "#"))] == []


@pytest.mark.parametrize("workflow", ["build.yml", "publish.yml"])
def test_workflows_install_the_wheel_by_its_file_name(workflow):
    """wheel のファイル名は配布名から作られる。配布名を変えたら CI の glob も変える。"""
    wheel_prefix = re.sub(r"[-_.]+", "_", PYPROJECT["project"]["name"]).lower() + "-"
    text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    globs = re.findall(r"([\w.]+-)\*\.whl", text)

    assert globs and set(globs) == {wheel_prefix}
