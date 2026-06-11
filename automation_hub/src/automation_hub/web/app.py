from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Automation Hub")

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
