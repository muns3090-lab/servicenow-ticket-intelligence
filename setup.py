from setuptools import setup, find_packages

setup(
    name="snow-analyzer",
    version="1.0.0",
    description="ServiceNow Ops Analyzer — classify, cluster, and report on ticket data",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
        "scipy>=1.11.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "tabulate>=0.9.0",
        "colorama>=0.4.6",
    ],
    entry_points={
        "console_scripts": [
            "snow-analyzer=main:cli",
        ],
    },
)
