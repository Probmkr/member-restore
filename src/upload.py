from json import load
from threading import local
from lib import DATA_PATH
from utils import FileManager
from dotenv import load_dotenv
import os

load_dotenv()

file = FileManager(os.getenv("GOOGLE_DRIVE_DATA_URL"),
                   os.getenv("GOOGLE_DRIVE_BACKUP_URL"))

local_data = open(DATA_PATH, "r")

file.save(load(local_data))
