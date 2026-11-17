"""Launch the dashboard or explicitly prepare its fixed-population models."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Painel do Mercado Residencial de Belo Horizonte (ITBI)"
    )
    parser.add_argument("command", nargs="?", choices=["serve", "prepare"], default="serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument(
        "--force", action="store_true", help="Reconstrói dados e modelos locais"
    )
    args = parser.parse_args()
    if args.command == "prepare":
        import json

        from threadpoolctl import threadpool_limits

        from bh_itbi.data import load_transactions, prepare_cache
        from bh_itbi.models import prepare_models

        if args.force:
            prepare_cache()
        data = load_transactions()
        with threadpool_limits(limits=2):
            metadata = prepare_models(data, force=args.force)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    else:
        from bh_itbi.app import create_app

        app = create_app()
        app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
