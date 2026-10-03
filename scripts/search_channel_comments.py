import subprocess
import json

video_ids = ['_ziYSeuUIiw', 'gMu1aoU0Puc', '7a6SGQg1HaI', 'S7Rqy8iAbP8', 'iRBllumLj-g', 'p28Wq3c45dE', 'RS96aEzBTdI']
keywords = ['voice', 'ai', 'tts', 'eleven', 'narrat', 'who is', 'capcut', 'speech', 'clone', 'sound like', 'what is this voice']

for vid in video_ids:
    cmd = ['yt-dlp', '--write-comments', '--dump-json', f'https://youtube.com/shorts/{vid}']
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if res.stdout:
        try:
            d = json.loads(res.stdout)
            comments = d.get('comments', [])
            print(f'Checked {vid}: {len(comments)} comments')
            for c in comments:
                t = c.get('text', '')
                if any(k in t.lower() for k in keywords):
                    print(f"[{c.get('author')} on {vid}]: {t}\n")
        except Exception as e:
            print(f"Error parsing {vid}: {e}")
