from tau_emotion.utils.utils import DATA_DIR

AIRLINE_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "airline"
AIRLINE_DB_PATH = AIRLINE_DATA_DIR / "db.json"
AIRLINE_POLICY_PATH = AIRLINE_DATA_DIR / "policy.md"
AIRLINE_TASK_SET_PATH = AIRLINE_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
AIRLINE_TRAIN_DB_PATH = AIRLINE_DATA_DIR / "db_train.json"
AIRLINE_TRAIN_TASK_SET_PATH = AIRLINE_DATA_DIR / "tasks_train.json"
