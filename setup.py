import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="miney",
    version="0.1.2",
    author="Robert Lieback",
    author_email="robertlieback@zetabyte.de",
    description="The python interface to minetest",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/miney-py/miney",
    packages=["miney"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Topic :: Games/Entertainment"
    ],
    python_requires='>=3.6',
)
