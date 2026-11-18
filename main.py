"""Launch the dashboard or explicitly prepare its fixed-population models."""

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Belo Horizonte Residential Market Dashboard (ITBI)"
    )
    parser.add_argument("command", nargs="?", choices=["serve", "prepare"], default="serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--force", action="store_true", help="Rebuild local data and models")
    args = parser.parse_args()
    if args.command == "prepare":
        # Use only the build stack for preparation, and keep --help import-light.
        from threadpoolctl import threadpool_limits  # noqa: PLC0415

        from bh_itbi.data import load_transactions, prepare_cache  # noqa: PLC0415
        from bh_itbi.models import prepare_models  # noqa: PLC0415

        if args.force:
            prepare_cache()
        data = load_transactions()
        with threadpool_limits(limits=2):
            metadata = prepare_models(data, force=args.force)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    else:
        # Preparation and --help do not need to load Dash or the index template.
        from bh_itbi.app import create_app  # noqa: PLC0415

        app = create_app()
        app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
