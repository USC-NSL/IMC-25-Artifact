from setuptools import setup, find_packages

setup(
    name="warctradeoff",
    version="0.1.0",
    description="Warctradeoff package for IMC-25-Artifact",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "beautifulsoup4",
        "opencv-python",
        "publicsuffixlist",
        "paramiko",
        "scp",
        "esprima",
        "requests",
        "pandas",
        "diff_match_patch",
        "levenshtein",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)