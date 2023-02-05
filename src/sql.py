from utils import GDRIVE_SQL_DATA_FILE_ID, drive, SQL_DATA_PATH
from db import SqlBackupManager

sqlmgr = SqlBackupManager(GDRIVE_SQL_DATA_FILE_ID, SQL_DATA_PATH, drive)
sqlmgr.backup_from_database()
