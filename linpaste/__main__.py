"""Allow ``python -m linpaste`` to behave like the ``linpaste`` console script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
