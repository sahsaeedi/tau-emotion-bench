from tau_emotion.utils.utils import DATA_DIR

TELECOM_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "telecom"
TELECOM_DB_PATH = TELECOM_DATA_DIR / "db.json"
TELECOM_POLICY_PATH = TELECOM_DATA_DIR / "policy.md"
TELECOM_TASK_SET_PATH = TELECOM_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
TELECOM_TRAIN_DB_PATH = TELECOM_DATA_DIR / "db_train.json"
TELECOM_TRAIN_TASK_SET_PATH = TELECOM_DATA_DIR / "tasks_train.json"
