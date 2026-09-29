from tau_emotion.utils.utils import DATA_DIR

SCHOOL_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "school"
SCHOOL_DB_PATH = SCHOOL_DATA_DIR / "db.json"
SCHOOL_POLICY_PATH = SCHOOL_DATA_DIR / "policy.md"
SCHOOL_TASK_SET_PATH = SCHOOL_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
SCHOOL_TRAIN_DB_PATH = SCHOOL_DATA_DIR / "db_train.json"
SCHOOL_TRAIN_TASK_SET_PATH = SCHOOL_DATA_DIR / "tasks_train.json"
