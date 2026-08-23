"""Setuptools hook that marks the bundled-DLL wheel as Windows x64."""

from setuptools import setup
from setuptools.command.bdist_wheel import bdist_wheel


class WindowsBinaryWheel(bdist_wheel):
    """Emit one Python-independent, Windows-x64-only wheel."""

    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> tuple[str, str, str]:
        return "py3", "none", "win_amd64"


setup(cmdclass={"bdist_wheel": WindowsBinaryWheel})
