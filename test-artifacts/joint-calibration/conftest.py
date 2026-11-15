import os,sys,tempfile
_DB_DIR=tempfile.mkdtemp(prefix="pulp-joint-")
os.environ["DATABASE_URL"]="sqlite:///"+_DB_DIR+"/test.db"
os.environ["SEED_DEMO"]="false"
sys.path.insert(0,"/workspace/backend")
import pytest
from src.config.database import initialize,Session
initialize()
import src.services.run_service as run_service
run_service.enqueue=lambda run_id:None
@pytest.fixture()
def db():
 with Session() as session:yield session
