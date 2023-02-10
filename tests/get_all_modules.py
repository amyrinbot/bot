import os

rootdir = os.getcwd()
direc = os.path.join(rootdir, "modules")


for root, _, files in os.walk(direc):
    prefix = root[len(rootdir) + 1 :].replace("\\", "/").replace("/", ".")

    parent = prefix.split(".")[-1]
    if parent == "__pycache__":
        continue

    for file in files:
        fn = file[:-3]
        name = f"{prefix}.{fn}"
        print(name)
