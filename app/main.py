import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def main() -> None:
    if "--correlation" in sys.argv:
        from app.correlation_lab import launch_correlation_lab

        launch_correlation_lab()
        return

    from app.gui_app import launch_app

    launch_app()


if __name__ == "__main__":
    main()
