"""AWS Lambda entrypoint for the Mira FastAPI app."""

from mangum import Mangum

from api.main import app

handler = Mangum(app, lifespan="off")
