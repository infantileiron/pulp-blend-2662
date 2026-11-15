from sqlalchemy import String,Text,JSON,ForeignKey,Double,Integer
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class JointCalibration(RecordMixin,Base):
 __tablename__="calibrations"
 name:Mapped[str]=mapped_column(String(180),unique=True)
 measurement_set_id:Mapped[str]=mapped_column(ForeignKey("measurements.id"))
 source_version:Mapped[int]=mapped_column(Integer)
 status:Mapped[str]=mapped_column(String(20),default="draft")
 reason:Mapped[str]=mapped_column(Text,default="")
 keys:Mapped[list]=mapped_column(JSON,default=list)
 matrix:Mapped[list]=mapped_column(JSON,default=list)
 pair_counts:Mapped[list]=mapped_column(JSON,default=list)
 key_counts:Mapped[dict]=mapped_column(JSON,default=dict)
 min_eigenvalue:Mapped[float]=mapped_column(Double,nullable=True)
 method:Mapped[str]=mapped_column(String(300),default="")
 assumption:Mapped[str]=mapped_column(Text,default="")
