from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Clase base declarativa. Los modelos de app/models/ deben heredar de esta
    clase e importarse en app/db/base_all.py para que create_all los detecte."""
