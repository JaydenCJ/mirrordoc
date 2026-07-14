"""Allow ``python -m mirrordoc`` to behave exactly like the console script."""

from .cli import run

if __name__ == "__main__":
    run()
