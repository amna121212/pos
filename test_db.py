import os
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

credentials = dotenv_values(
    "/root/project-db-credentials.env"
)

password = credentials["POS_DB_PASSWORD"]

database_url = (
    "postgresql+psycopg://pos_app:"
    f"{quote(password, safe='')}"
    "@127.0.0.1:5432/retail_pos_db"
)

engine = create_engine(database_url)

with engine.connect() as connection:
    result = connection.execute(
        text("SELECT current_database(), current_user")
    )
    print("Database connection:", result.fetchone())
    print("POS SQLAlchemy connection successful!")
