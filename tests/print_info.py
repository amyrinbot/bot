from textwrap import indent

info = {
    "statistics": {"users": 4, "guilds": 1},
    "modules": {"commands": 8, "events": 48},
}


for name, data in info.items():
    print(f"{name}")
    for k, v in data.items():
        if k == list(data.keys())[-1]:
            text = f"└─ {k}: {v}"
        else:
            text = f"├─ {k}: {v}"
        print(indent(text, "  "))
