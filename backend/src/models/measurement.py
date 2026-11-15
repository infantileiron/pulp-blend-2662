from sqlalchemy import String,Text,JSON,Integer
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class MeasurementSet(RecordMixin,Base):
 __tablename__="measurements"
 name:Mapped[str]=mapped_column(String(180),unique=True)
 version:Mapped[int]=mapped_column(Integer,default=1)
 content_hash:Mapped[str]=mapped_column(String(64))
 rows:Mapped[list]=mapped_column(JSON)
 batches:Mapped[int]=mapped_column(Integer)
 description:Mapped[str]=mapped_column(Text,default="")
