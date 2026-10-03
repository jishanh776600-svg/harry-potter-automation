import json

with open('data/cache/beast_shots/real_movie_catalog.json', 'r', encoding='utf-8') as f:
    cat = json.load(f)

print(f"Total shots in catalog: {len(cat)}")
for s in cat:
    m = s.get('movie_number')
    st = s.get('start_seconds', 0)
    et = s.get('end_seconds', 0)
    if m == 8 and (6070 <= st <= 6200 or 6515 <= st <= 6555):
        sid = s.get('shot_id')
        actions = s.get('actions_depicted', [])
        objects = s.get('objects_present', [])
        desc = s.get('scene_description', '')
        print(f"Shot: {sid} | Time: {st:.2f}s - {et:.2f}s | Actions: {actions} | Objs: {objects} | Desc: {desc[:60]}")
