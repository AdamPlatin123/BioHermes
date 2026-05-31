"""Build the demo HTML page by embedding log data."""
import json
import os
import sys

log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_output", "logs")
html_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_output", "demo.html")

# Load all demo logs
demos = []
for i in range(1, 11):
    fname = f"demo_{i:02d}_*.json"
    import glob
    matches = glob.glob(os.path.join(log_dir, f"demo_{i:02d}_*.json"))
    if matches:
        with open(matches[0], encoding="utf-8") as f:
            demos.append(json.load(f))

print(f"Loaded {len(demos)} demo logs")

# Read HTML template
with open(html_path, encoding="utf-8") as f:
    html = f.read()

# Embed data
data_json = json.dumps(demos, ensure_ascii=False, indent=2)
html = html.replace("__DEMOS_PLACEHOLDER__", data_json)

# Write final HTML
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"HTML written to {html_path}")
print(f"Size: {len(html)} bytes, {len(demos)} demos embedded")
