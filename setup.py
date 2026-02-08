from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="py-attractor",
    version="0.3.0",
    description="A DOT-based pipeline runner for AI workflows",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Attractor Contributors",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "pyparsing>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "ruff>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "py-attractor=attractor.cli:main",
        ],
    },
)
