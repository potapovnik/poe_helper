Shared Config Tool (generic helper)

Files:
- shared_config.py: generic JSON config helper with atomic writes
- config_example.json: sample JSON structure

Example use in an unrelated Python application:

    from shared_config import SharedConfig

    cfg = SharedConfig("config.json", defaults={"enabled": True, "count": 1})
    print(cfg.get("enabled"))
    cfg.set("count", 2)
    cfg.save()

For two independent apps to share ordinary settings, both must use the same config
file path and call reload() before reading values that may have changed elsewhere.
This package is not connected to any game automation or gameplay loop.
