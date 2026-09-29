from tau_emotion.utils.utils import DATA_DIR

TELEHEALTH_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "telehealth"
TELEHEALTH_DB_PATH = TELEHEALTH_DATA_DIR / "db.json"
TELEHEALTH_POLICY_PATH = TELEHEALTH_DATA_DIR / "policy.md"
TELEHEALTH_TASK_SET_PATH = TELEHEALTH_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
TELEHEALTH_TRAIN_DB_PATH = TELEHEALTH_DATA_DIR / "db_train.json"
TELEHEALTH_TRAIN_TASK_SET_PATH = TELEHEALTH_DATA_DIR / "tasks_train.json"
