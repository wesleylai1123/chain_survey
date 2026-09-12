import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def main() -> None:
    if "--collection-progress" in sys.argv:
        from app.collection_progress_dashboard import launch_collection_progress_dashboard

        launch_collection_progress_dashboard()
        return

    if "--factor-robustness" in sys.argv:
        from app.factor_robustness_lab import launch_factor_robustness_lab

        launch_factor_robustness_lab()
        return

    if "--factor-validation" in sys.argv:
        from app.factor_validation_lab import launch_factor_validation_lab

        launch_factor_validation_lab()
        return

    if "--panel-correlation" in sys.argv:
        from app.panel_correlation_lab import launch_panel_correlation_lab

        launch_panel_correlation_lab()
        return

    if "--correlation" in sys.argv:
        from app.correlation_lab import launch_correlation_lab

        launch_correlation_lab()
        return

    from app.gui_app import launch_app

    launch_app()


if __name__ == "__main__":
    main()
