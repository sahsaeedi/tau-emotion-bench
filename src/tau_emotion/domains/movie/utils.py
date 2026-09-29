from tau_emotion.utils.utils import DATA_DIR

MOVIE_DATA_DIR = DATA_DIR / "tau_emotion" / "domains" / "movie"
MOVIE_DB_PATH = MOVIE_DATA_DIR / "db.json"
MOVIE_POLICY_PATH = MOVIE_DATA_DIR / "policy.md"
MOVIE_TASK_SET_PATH = MOVIE_DATA_DIR / "tasks.json"

# Training data, built from TRACER's train data (docs/train_tasks.md).
MOVIE_TRAIN_DB_PATH = MOVIE_DATA_DIR / "db_train.json"
MOVIE_TRAIN_TASK_SET_PATH = MOVIE_DATA_DIR / "tasks_train.json"
