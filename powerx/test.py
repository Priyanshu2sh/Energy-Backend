import re

path = "C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\powerx\\Month_ahead_clean.ipynb"
content = open(path, "rb").read()
clean = re.sub(b'[\x80-\x9F]', b' ', content)
open(path, "wb").write(clean)

print("✅ Removed control chars safely")
