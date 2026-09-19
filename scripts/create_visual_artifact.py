from PIL import Image, ImageDraw, ImageFont

# Load reference screenshots and resize to 1080x1920
ref1 = Image.open(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36\.user_uploaded\media_1789799977742.jpg").resize((1080, 1920), Image.Resampling.LANCZOS)
ref2 = Image.open(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36\.user_uploaded\media_1789799985293.jpg").resize((1080, 1920), Image.Resampling.LANCZOS)

# Load our rendered frames
rend1 = Image.open("data/subtitles/precise_hogwarts_on_bg.png")
rend2 = Image.open("data/subtitles/precise_castle_on_bg.png")
rend_val = Image.open("data/subtitles/precise_validation_2lines_on_bg.png")

# Crop zoomed subtitle regions (y: 950 to 1250, x: 100 to 980) -> 880x300
crop_ref1 = ref1.crop((100, 960, 980, 1260))
crop_rend1 = rend1.crop((100, 960, 980, 1260))

crop_ref2 = ref2.crop((100, 960, 980, 1260))
crop_rend2 = rend2.crop((100, 960, 980, 1260))

crop_val = rend_val.crop((100, 900, 980, 1260))

# Build a master comparison canvas (width: 1800, height: 1600)
canvas = Image.new("RGB", (1820, 1500), (18, 18, 20))
d = ImageDraw.Draw(canvas)

# Title Header
d.rectangle([(0, 0), (1820, 70)], fill=(28, 28, 35))
d.text((30, 20), "HARRY POTTER SHORTS SUBTITLE TEMPLATE — VISUAL VERIFICATION", fill=(255, 215, 0))

# Section 1: Hogwarts kitchens
d.text((30, 90), "REFERENCE 1 (Screenshot)", fill=(200, 200, 200))
canvas.paste(crop_ref1, (30, 120))

d.text((930, 90), "TEMPLATE RENDER 1 (Harry P Font, Size 84, Outline 4.5, Center-Aligned)", fill=(0, 255, 150))
canvas.paste(crop_rend1, (930, 120))

# Section 2: the castle
d.text((30, 450), "REFERENCE 2 (Screenshot)", fill=(200, 200, 200))
canvas.paste(crop_ref2, (30, 480))

d.text((930, 450), "TEMPLATE RENDER 2 (Harry P Font, Size 84, Outline 4.5, Center-Aligned)", fill=(0, 255, 150))
canvas.paste(crop_rend2, (930, 480))

# Section 3: Validation Sentence
d.text((30, 810), "VALIDATION SENTENCE ON FULL MOVIE FRAME: \"Harry Potter had no idea what was waiting for him.\"", fill=(255, 215, 0))
canvas.paste(crop_val, (470, 850))

# Save artifact
out_path = "data/subtitles/visual_verification_matrix.png"
canvas.save(out_path)
print(f"Master verification matrix saved to: {out_path}")
