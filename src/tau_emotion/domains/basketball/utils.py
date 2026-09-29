from tau_emotion.utils.utils import DATA_DIR

BASKETBALL_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "basketball"
BASKETBALL_DB_PATH = BASKETBALL_DATA_DIR / "db.json"
BASKETBALL_POLICY_PATH = BASKETBALL_DATA_DIR / "policy.md"
BASKETBALL_TASK_SET_PATH = BASKETBALL_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
BASKETBALL_TRAIN_DB_PATH = BASKETBALL_DATA_DIR / "db_train.json"
BASKETBALL_TRAIN_TASK_SET_PATH = BASKETBALL_DATA_DIR / "tasks_train.json"
