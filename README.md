
# dacite-retrofit

A [dacite][dacite-repo] fork with [PEP 585][pep-585] & [PEP 604][pep-604] typehint
support in Python 3.8+. See the original project for documentation.

## Installation

`dacite-retrofit` is available on PyPI:
```
pip install dacite-retrofit
```

It can also be installed from source:
```
pip install git+https://github.com/trag1c/dacite-retrofit.git
```

> [!Warning]
> Unlike `dacite` (which supports Python 3.6+), `dacite-retrofit` only supports
> Python 3.8+.

## Development
This fork uses `poetry`, `black`, `mypy`, `pytest` and `isort`:
```console
$ poetry run black .
$ poetry run mypy dacite
$ poetry run pytest --cov dacite
$ poetry run isort .
```

Originally created by [Konrad Hałas][halas-homepage].

[dacite-repo]: https://github.com/konradhalas/dacite
[pep-585]: https://www.python.org/dev/peps/pep-0585/
[pep-604]: https://www.python.org/dev/peps/pep-0604/
[halas-homepage]: https://konradhalas.pl
