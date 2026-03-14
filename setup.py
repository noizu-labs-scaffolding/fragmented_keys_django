"""Setup configuration for fragmented_keys_django."""

from setuptools import setup, find_packages

setup(
    name="fragmented-keys-django",
    version="0.1.0",
    description="Django cache integration with fragmented_keys for automatic invalidation",
    long_description="""A Django cache backend adapter and utilities for the fragmented_keys library,
providing automatic cache invalidation through versioned tag-instance pairs.""",
    license="MIT",
    author="GreatNonProfit",
    packages=find_packages(),
    install_requires=[
        "Django>=3.2",
        "fragmented-keys>=1.1",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
)