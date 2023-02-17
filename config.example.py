import os

censored = [
    "TOKEN",
    "IPC_SECRET_KEY",
    "MYSTBIN_API",
    "socialclub.password",
    "database.password",
]

TOKEN = ""
IPC_SECRET_KEY = ""
MYSTBIN_API = ""
DEBUG = True
MEDIASERVER_KEY = ""
ALLOWED_ON_DEBUG = (...,)
OWNERS = (...,)


class socialclub:
    username: str = ""
    password: str = ""


class nginx:
    url: str = "http://127.0.0.1:8080"
    path: os.PathLike = "/home/amyrin/usercontent"


class database:
    user: str = "user"
    password: str = "password"
    name: str = "amyrin"
    host: str = "127.0.0.1"
    port: str = "5432"
