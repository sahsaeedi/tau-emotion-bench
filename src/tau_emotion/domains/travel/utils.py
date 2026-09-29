from tau_emotion.utils.utils import DATA_DIR

TRAVEL_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "travel"
TRAVEL_DB_PATH = TRAVEL_DATA_DIR / "db.json"
TRAVEL_POLICY_PATH = TRAVEL_DATA_DIR / "policy.md"
TRAVEL_TASK_SET_PATH = TRAVEL_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
TRAVEL_TRAIN_DB_PATH = TRAVEL_DATA_DIR / "db_train.json"
TRAVEL_TRAIN_TASK_SET_PATH = TRAVEL_DATA_DIR / "tasks_train.json"
