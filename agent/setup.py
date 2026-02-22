"""Setup for AEM Experience Modernization Agent."""
from setuptools import setup, find_packages

setup(
    name="aem-modernization-agent",
    version="1.0.0",
    description="AI-powered Experience Modernization Agent for Traditional AEM",
    author="AEM Modernization Team",
    python_requires=">=3.10",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "anthropic>=0.39.0",
        "pyyaml>=6.0.1",
        "jinja2>=3.1.3",
        "click>=8.1.7",
        "beautifulsoup4>=4.12.3",
        "requests>=2.31.0",
        "lxml>=5.1.0",
        "httpx>=0.27.0",
        "Pillow>=10.2.0",
        "rich>=13.7.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "aem-modernize=main:cli",
        ],
    },
)
