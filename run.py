from app import create_app


app = create_app()


if __name__ == "__main__":
    # debug is convenient for local development; disable via FLASK_DEBUG=0
    import os

    debug = os.getenv("FLASK_DEBUG", "1") not in {"0", "false", "False", ""}
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=debug)

