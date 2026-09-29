from tau_emotion.utils.utils import DATA_DIR

RETAIL_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "retail"
RETAIL_DB_PATH = RETAIL_DATA_DIR / "db.json"
RETAIL_POLICY_PATH = RETAIL_DATA_DIR / "policy.md"
RETAIL_TASK_SET_PATH = RETAIL_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
RETAIL_TRAIN_DB_PATH = RETAIL_DATA_DIR / "db_train.json"
RETAIL_TRAIN_TASK_SET_PATH = RETAIL_DATA_DIR / "tasks_train.json"
