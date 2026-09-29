from tau_emotion.utils.utils import DATA_DIR

RESTAURANT_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "restaurant"
RESTAURANT_DB_PATH = RESTAURANT_DATA_DIR / "db.json"
RESTAURANT_POLICY_PATH = RESTAURANT_DATA_DIR / "policy.md"
RESTAURANT_TASK_SET_PATH = RESTAURANT_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
RESTAURANT_TRAIN_DB_PATH = RESTAURANT_DATA_DIR / "db_train.json"
RESTAURANT_TRAIN_TASK_SET_PATH = RESTAURANT_DATA_DIR / "tasks_train.json"
