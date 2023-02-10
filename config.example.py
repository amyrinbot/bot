import os

TOKEN = ''
IPC_SECRET_KEY = ''
MYSTBIN_API = ''
DEBUG = True
MEDIASERVER_KEY = ''
ALLOWED_ON_DEBUG = (...,)
OWNERS = (...,)

class Nginx:
    url: str = "http://127.0.0.1:8080"
    path: os.PathLike = "/home/amyrin/usercontent"