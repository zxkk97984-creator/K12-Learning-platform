"""Standalone Worker process entry point (``python -m app.worker``)."""

from app.jobs.worker import main


if __name__ == "__main__":  # pragma: no cover
    main()
