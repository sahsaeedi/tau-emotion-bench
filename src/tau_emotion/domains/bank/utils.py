from tau_emotion.utils.utils import DATA_DIR

BANK_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "bank"
BANK_DB_PATH = BANK_DATA_DIR / "db.json"
BANK_POLICY_PATH = BANK_DATA_DIR / "policy.md"
BANK_TASK_SET_PATH = BANK_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
BANK_TRAIN_DB_PATH = BANK_DATA_DIR / "db_train.json"
BANK_TRAIN_TASK_SET_PATH = BANK_DATA_DIR / "tasks_train.json"
