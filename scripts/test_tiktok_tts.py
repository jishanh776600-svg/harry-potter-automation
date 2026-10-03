import requests
import base64

endpoint = 'https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/'
text = 'Do you know why Professor Snape always seemed unhappy?'
voices = [
    'en_male_narration',
    'en_us_006',
    'en_us_010',
    'en_male_cody',
    'en_male_funny',
    'en_male_jomboy',
]

headers = {
    'User-Agent': 'com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_ES; SM-G988N; Build/NRD90M;tt-ok/3.12.13.1)',
}

for v in voices:
    try:
        url = f'{endpoint}?text_speaker={v}&req_text={requests.utils.quote(text)}&speaker_map_type=0&aid=1233'
        resp = requests.post(url, headers=headers, timeout=6)
        res_json = resp.json()
        status = res_json.get('status_code')
        msg = res_json.get('message')
        print(f"Voice {v}: status={status}, msg={msg}")
        v_str = res_json.get('data', {}).get('v_str')
        if v_str:
            audio_bytes = base64.b64decode(v_str)
            target = f'data/reference_analysis/tiktok_{v}.mp3'
            with open(target, 'wb') as f:
                f.write(audio_bytes)
            print(f"Saved {target} ({len(audio_bytes)} bytes)")
    except Exception as e:
        print(f"Voice {v} error: {e}")
