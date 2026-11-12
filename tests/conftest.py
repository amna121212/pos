import pytest

from app import create_app, db


@pytest.fixture(scope="session", autouse=True)
def app():
    application = create_app()
    with application.app_context():
        yield application
        db.session.remove()
