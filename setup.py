"""Build the platform-native pathfinding library into Python wheels."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py
from setuptools.errors import ExecError


class PlatformDistribution(Distribution):
    """Mark wheels as platform-specific because they contain a shared library."""

    def has_ext_modules(self) -> bool:
        """Report that the distribution contains native machine code.

        Returns:
            Always true so wheel tooling emits a platform-specific wheel.
        """
        return True


class BuildPythonWithNative(build_py):
    """Build and copy the Xmake shared library into the wheel tree."""

    def run(self) -> None:
        """Build Python modules and their native pathfinding library.

        Raises:
            ExecError: Xmake failed or did not produce exactly one library.
        """
        repository = Path(__file__).resolve().parent

        try:
            subprocess.run(
                ["xmake", "f", "-c", "-m", "release", "--toolchain=clang"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["xmake", "build", "pacman-native"],
                cwd=repository,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise ExecError("failed to build pacman-native with Xmake") from error

        shared_library_names = {
            "libpacman-native.so",
            "libpacman-native.dylib",
            "pacman-native.dll",
        }
        libraries = tuple(
            path
            for path in (repository / "build").glob("*/*/release/*")
            if path.is_file() and path.name in shared_library_names
        )

        if len(libraries) != 1:
            raise ExecError(f"expected one pacman-native shared library, found {len(libraries)}")

        super().run()

        destination = Path(self.build_lib) / "pacman" / "analyze" / "lib"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(libraries[0], destination / libraries[0].name)


class PlatformAbiWheel(bdist_wheel):
    """Tag the ctypes library as Python-ABI-independent and platform-specific."""

    def get_tag(self) -> tuple[str, str, str]:
        """Return the broad Python tag and the detected native platform tag.

        Returns:
            A ``py3-none-<platform>`` wheel compatibility tag.
        """
        _, _, platform = super().get_tag()
        return "py3", "none", platform


setup(
    cmdclass={
        "bdist_wheel": PlatformAbiWheel,
        "build_py": BuildPythonWithNative,
    },
    distclass=PlatformDistribution,
)
