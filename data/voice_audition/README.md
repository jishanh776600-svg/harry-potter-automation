# Harry Potter Channel — Bella (Kokoro af_bella) Voice Audition Library

> **Purpose**: Comparative evaluation of 16 delivery profiles and 3 intensity levels using Kokoro-82M `af_bella`.
> All samples use **identical -15.5 LUFS ITU-R BS.1770 broadcast loudness normalization** to guarantee an unbiased, fair comparison.
> The underlying voice identity remains 100% Bella (`af_bella`); only directorial performance parameters (speed, pause timing, cadence, EQ presence) vary.

## Summary Statistics
- **Total Delivery Profiles**: 16
- **Total Audition Audio Samples**: 48
- **Voice Identity**: `af_bella` (Kokoro-82M ONNX)
- **Audition Library Location**: `data/voice_audition/bella/`
- **Metadata Specification**: `data/voice_audition/bella_profiles_metadata.json`

---

## Audition Profiles & Sample Index

### BELLA_CANONICAL
- **Description**: Natural baseline narration: balanced conversational flow with clear neutral cadence.
- **Content Affinity**: Standard channel voiceover, balanced storytelling
- **Directory**: `data/voice_audition/bella/canonical/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_canonical_low_01.wav` | **LOW** | 0.98x | 0.28s | 0.10s | 6.81s | "Every young wizard who steps into Diagon Alley remembers the smell of fresh parchment and polished wand wood." |
| `bella_canonical_medium_02.wav` | **MEDIUM** | 1.00x | 0.25s | 0.09s | 6.38s | "For ten quiet years, Harry lived without knowing that his parents had been two of the bravest sorcerers in Britain." |
| `bella_canonical_high_03.wav` | **HIGH** | 1.02x | 0.22s | 0.08s | 7.53s | "Hogwarts castle has stood for over a thousand years, guarding ancient secrets that even the headmaster cannot fully unlock." |

### BELLA_CINEMATIC
- **Description**: Cinematic storytelling: controlled emotion, rich depth, cinematic pauses.
- **Content Affinity**: Novel story arcs, epic wizarding lore, high-production storytelling
- **Directory**: `data/voice_audition/bella/cinematic/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_cinematic_low_01.wav` | **LOW** | 0.96x | 0.32s | 0.12s | 6.25s | "Rain lashed against the black glass of the Hogwarts Express as it glided into the misty Scottish Highlands." |
| `bella_cinematic_medium_02.wav` | **MEDIUM** | 0.94x | 0.35s | 0.14s | 7.62s | "Far below the stone dungeons, shadows gathered around the mirror of Erised, waiting for a heart pure enough to look inside." |
| `bella_cinematic_high_03.wav` | **HIGH** | 0.92x | 0.40s | 0.15s | 8.32s | "When the great hall doors swung open, hundreds of floating candles illuminated the starry sky ceiling above the four house tables." |

### BELLA_DISCOVERY
- **Description**: Curiosity narration: engaging reveal, slight excitement, brisk explanatory pace.
- **Content Affinity**: Things movies didn't explain, magical artifact secrets
- **Directory**: `data/voice_audition/bella/discovery/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_discovery_low_01.wav` | **LOW** | 1.00x | 0.24s | 0.09s | 6.49s | "Here is an incredible detail the movies completely left out about how the Marauder's Map was actually created." |
| `bella_discovery_medium_02.wav` | **MEDIUM** | 1.03x | 0.20s | 0.08s | 5.61s | "Did you know that Ollivander tested Harry Potter with twenty different wands before the phoenix feather chose him?" |
| `bella_discovery_high_03.wav` | **HIGH** | 1.06x | 0.18s | 0.07s | 7.89s | "The movies never explained this, but Peeves the Poltergeist was actually born from the chaotic energy of medieval Hogwarts students!" |

### BELLA_DRAMATIC
- **Description**: Dramatic narration: strong emotional impact, palpable tension, restrained power.
- **Content Affinity**: Crucial story turning points, confrontations, grave peril
- **Directory**: `data/voice_audition/bella/dramatic/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_dramatic_low_01.wav` | **LOW** | 0.95x | 0.30s | 0.12s | 6.63s | "Uncle Vernon bolted three deadbolts onto Harry's door, desperate to lock the magical world outside forever." |
| `bella_dramatic_medium_02.wav` | **MEDIUM** | 0.92x | 0.36s | 0.14s | 6.95s | "Deep inside the forbidden third floor corridor, a giant three-headed beast stood guarding a secret trapdoor." |
| `bella_dramatic_high_03.wav` | **HIGH** | 0.89x | 0.42s | 0.16s | 8.53s | "A blinding green flash shattered the cottage in Godric's Hollow, leaving only a crying infant and a splintered wand on the floor." |

### BELLA_WARM
- **Description**: Warm narration: nostalgic, human, heartfelt warmth and fond remembrance.
- **Content Affinity**: Friendship milestones, Christmas at Hogwarts, family moments
- **Directory**: `data/voice_audition/bella/warm/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_warm_low_01.wav` | **LOW** | 0.98x | 0.28s | 0.11s | 7.96s | "Mrs. Weasley knit a thick maroon jumper with a hand-stitched letter H, giving Harry his very first real Christmas present." |
| `bella_warm_medium_02.wav` | **MEDIUM** | 0.96x | 0.30s | 0.12s | 7.17s | "Hagrid handed Harry a slightly squashed chocolate cake with words piped in green icing: Happee Birthdae Harry." |
| `bella_warm_high_03.wav` | **HIGH** | 0.94x | 0.34s | 0.13s | 7.70s | "Sitting together by the roaring Gryffindor common room fire, Harry finally realized he wasn't alone in the world anymore." |

### BELLA_CALM
- **Description**: Calm narration: composed, steady, reassuring clarity.
- **Content Affinity**: Dumbledore's wisdom, ancient magical artifacts lore
- **Directory**: `data/voice_audition/bella/calm/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_calm_low_01.wav` | **LOW** | 0.96x | 0.30s | 0.12s | 7.21s | "The silver instruments on Dumbledore's desk whirred quietly, puffing tiny rings of pale smoke into the quiet night." |
| `bella_calm_medium_02.wav` | **MEDIUM** | 0.93x | 0.35s | 0.13s | 6.59s | "Snow fell softly over the rooftops of Hogsmeade, coating the cobblestones in a peaceful blanket of white." |
| `bella_calm_high_03.wav` | **HIGH** | 0.90x | 0.38s | 0.15s | 6.72s | "Down in the potion master's cellar, ancient glass vials caught the dim torchlight without a single sound." |

### BELLA_SUSPENSE
- **Description**: Suspense narration: heavy anticipation, deliberate pregnant pauses, brooding tension.
- **Content Affinity**: Dark corridors, listening for footsteps, unseen dangers
- **Directory**: `data/voice_audition/bella/suspense/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_suspense_low_01.wav` | **LOW** | 0.94x | 0.36s | 0.14s | 5.78s | "Something shifted in the deep shadows beneath the restricted section bookshelves, just out of sight." |
| `bella_suspense_medium_02.wav` | **MEDIUM** | 0.90x | 0.42s | 0.16s | 6.29s | "Harry listened closely... Footsteps echoed on the cold flagstones above, slow and deliberate." |
| `bella_suspense_high_03.wav` | **HIGH** | 0.87x | 0.48s | 0.18s | 5.63s | "The silver doorknob began to turn on its own, inch by inch, into total darkness." |

### BELLA_SURPRISED
- **Description**: Surprised narration: genuine astonishment, wide-eyed revelation inflection.
- **Content Affinity**: Omitted scenes, surprising plot twists
- **Directory**: `data/voice_audition/bella/surprised/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_surprised_low_01.wav` | **LOW** | 1.02x | 0.22s | 0.08s | 7.02s | "Wait... Look closely at the portrait behind Dumbledore's chair, because that wizard is actually awake and taking notes!" |
| `bella_surprised_medium_02.wav` | **MEDIUM** | 1.05x | 0.19s | 0.07s | 6.49s | "You won't believe how different Ron Weasley was in the books; he was actually the strategic mastermind of the trio!" |
| `bella_surprised_high_03.wav` | **HIGH** | 1.08x | 0.16s | 0.06s | 6.51s | "The moving staircase didn't just change directions by chance... It was actively guiding Harry straight to the third floor!" |

### BELLA_EXCITED
- **Description**: Excited narration: high-energy momentum, punchy Quidditch-style excitement.
- **Content Affinity**: Quidditch match action, magical discoveries
- **Directory**: `data/voice_audition/bella/excited/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_excited_low_01.wav` | **LOW** | 1.04x | 0.20s | 0.08s | 5.57s | "Harry kicked hard off the grass, and the Nimbus Two Thousand surged upward into the clear blue sky!" |
| `bella_excited_medium_02.wav` | **MEDIUM** | 1.08x | 0.17s | 0.06s | 6.31s | "Look at that Quidditch play! Harry dives headfirst through the rain, tracking the golden snitch at ninety miles an hour!" |
| `bella_excited_high_03.wav` | **HIGH** | 1.12x | 0.14s | 0.05s | 6.53s | "Gryffindor wins the house cup! The entire great hall erupts into roaring cheers as the scarlet banners drop!" |

### BELLA_SAD
- **Description**: Sad narration: deep sorrow, poignant pauses, delicate resonance.
- **Content Affinity**: Mirror of Erised grief, lost parents, bittersweet moments
- **Directory**: `data/voice_audition/bella/sad/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_sad_low_01.wav` | **LOW** | 0.95x | 0.32s | 0.13s | 6.53s | "Harry sat alone in the dark dormitory, tracing the worn edges of the only photograph he had of his mother." |
| `bella_sad_medium_02.wav` | **MEDIUM** | 0.91x | 0.38s | 0.15s | 6.59s | "In the mirror of Erised, Harry saw his family smiling beside him, knowing none of them could ever come back." |
| `bella_sad_high_03.wav` | **HIGH** | 0.88x | 0.44s | 0.17s | 7.96s | "Hedwig rested her soft feathered head against the cage bars, watching Harry endure another lonely summer at Privet Drive." |

### BELLA_ANGRY
- **Description**: Angry narration: cutting edge, fierce confrontation, righteous anger.
- **Content Affinity**: Standing up to bullies, confronting betrayal
- **Directory**: `data/voice_audition/bella/angry/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_angry_low_01.wav` | **LOW** | 1.00x | 0.22s | 0.09s | 5.76s | "Aunt Petunia claimed her sister was a freak, refusing to ever speak Lily Potter's name aloud." |
| `bella_angry_medium_02.wav` | **MEDIUM** | 1.04x | 0.18s | 0.07s | 5.99s | "Uncle Vernon tore Harry's Hogwarts letter into tiny shreds right in front of his face with a bitter smirk." |
| `bella_angry_high_03.wav` | **HIGH** | 1.08x | 0.15s | 0.06s | 5.46s | "Malfoy snatched Neville's remembrall and taunted him across the courtyard until Harry had had enough!" |

### BELLA_DARK
- **Description**: Dark narration: chilling restraint, deep menacing tone.
- **Content Affinity**: Voldemort whispers, death eater plots, cursed blood
- **Directory**: `data/voice_audition/bella/dark/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_dark_low_01.wav` | **LOW** | 0.93x | 0.35s | 0.14s | 6.93s | "Knockturn Alley smelled of damp moss and poisonous toadstools, where dark wizards traded under hooded cloaks." |
| `bella_dark_medium_02.wav` | **MEDIUM** | 0.89x | 0.40s | 0.16s | 6.98s | "A withered hand resting on a black cushion in Borgin and Burkes suddenly twitched under the dim candlelight." |
| `bella_dark_high_03.wav` | **HIGH** | 0.86x | 0.45s | 0.18s | 8.26s | "The dark lord's whispered voice echoed from beneath Quirrell's turban, demanding absolute obedience in the cold dungeon." |

### BELLA_SARCASTIC
- **Description**: Sarcastic narration: knowing chuckle, witty mockery, sharp comedic timing.
- **Content Affinity**: Hermione's priority logic, Dudley's absurd tantrums
- **Directory**: `data/voice_audition/bella/sarcastic/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_sarcastic_low_01.wav` | **LOW** | 0.99x | 0.26s | 0.11s | 8.34s | "Uncle Vernon's brilliant plan to escape magical owls was hiding in an abandoned shack surrounded by freezing ocean waves." |
| `bella_sarcastic_medium_02.wav` | **MEDIUM** | 1.01x | 0.24s | 0.12s | 6.57s | "Because of course locking a boy under the stairs for a decade is definitely how you stop magic from existing." |
| `bella_sarcastic_high_03.wav` | **HIGH** | 1.03x | 0.22s | 0.13s | 7.10s | "Hermione honestly believed getting expelled from school was worse than getting eaten alive by a three-headed dog." |

### BELLA_EDUCATIONAL
- **Description**: Educational narration: authoritative teacher cadence, crisp, engaging explainer.
- **Content Affinity**: Animagus vs transfiguration distinctions, house lore
- **Directory**: `data/voice_audition/bella/educational/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_educational_low_01.wav` | **LOW** | 0.98x | 0.28s | 0.11s | 7.49s | "In wizarding lore, wand cores react directly to the caster's character; phoenix feathers demand great independence." |
| `bella_educational_medium_02.wav` | **MEDIUM** | 1.01x | 0.24s | 0.09s | 8.70s | "Here is the exact distinction: animagi retain their human minds, while wizards transformed by transfiguration lose all human thought." |
| `bella_educational_high_03.wav` | **HIGH** | 1.03x | 0.20s | 0.08s | 9.54s | "The four Hogwarts houses represent the four classical alchemical elements: Gryffindor fire, Ravenclaw air, Hufflepuff earth, and Slytherin water." |

### BELLA_FAST_ENERGETIC
- **Description**: Fast energetic narration: modern creator punch, high retention hook momentum.
- **Content Affinity**: Action recaps, urgent 25-second Shorts storytelling
- **Directory**: `data/voice_audition/bella/fast_energetic/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_fast_energetic_low_01.wav` | **LOW** | 1.06x | 0.18s | 0.07s | 6.61s | "Letters are flying down the chimney, owls are circling the roof, and Vernon Dursley is officially losing his mind!" |
| `bella_fast_energetic_medium_02.wav` | **MEDIUM** | 1.10x | 0.15s | 0.06s | 5.74s | "Three seconds on the clock, Harry dives right, snatches the snitch out of thin air, and seals the match!" |
| `bella_fast_energetic_high_03.wav` | **HIGH** | 1.14x | 0.12s | 0.05s | 6.25s | "Boom! Hagrid kicks the wooden door down, bends the shotgun in half, and hands Harry a chocolate birthday cake!" |

### BELLA_EMOTIONAL_RESTRAINED
- **Description**: Emotional restrained: profound vulnerability, subtle emotional quiver, dignified restraint.
- **Content Affinity**: Whispering to the mirror, holding the worn sweater
- **Directory**: `data/voice_audition/bella/emotional_restrained/`

| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `bella_emotional_restrained_low_01.wav` | **LOW** | 0.96x | 0.32s | 0.12s | 6.34s | "Lily's eyes looked back at Harry from the glass, carrying a warmth he had never felt in all his eleven years." |
| `bella_emotional_restrained_medium_02.wav` | **MEDIUM** | 0.93x | 0.36s | 0.14s | 7.08s | "Harry held the worn sweater close to his chest in the dark, whispering a quiet thank you to a mother he barely remembered." |
| `bella_emotional_restrained_high_03.wav` | **HIGH** | 0.90x | 0.42s | 0.16s | 6.34s | "He didn't care about being famous or defeating a dark lord; he just wanted his family to be alive." |

---

## Technical Controls Supported by Kokoro Implementation

1. **Pacing / Speed**: Directly controlled via Kokoro ONNX inference engine (`speed` parameter from 0.86x to 1.14x).
2. **Sentence Pauses**: Controlled via Kokoro `sentence_pause` parameter (0.12s to 0.48s), defining pauses between sentences.
3. **Clause / Comma Pauses**: Controlled via Kokoro `clause_pause` parameter (0.05s to 0.18s), governing punctuation breathing spaces.
4. **Punctuation Phrasing**: Modulated via punctuation syntax (`...`, `!`, `?`, `—`, `,`) to naturally guide neural prosody.
5. **Vocal Presence EQ**: Studio highpass (80 Hz) and parametric vocal presence boost (+1.5 dB to +3.2 dB @ 2500–3500 Hz).
6. **Broadcast Loudness Normalization**: ITU-R BS.1770 loudnorm filter at -15.5 LUFS with -1.2 dB true peak ceiling.

## Technical Limitations / Controls Not Feasible in Raw Kokoro

- **Independent Pitch Shifter**: Kokoro ONNX does not expose a native pitch slider in its neural synthesis head. Pitch differences are naturally driven by text prosody/punctuation and shaped by EQ formant frequencies.
- **Theatrical Whispering / Shouting**: Kokoro-82M synthesizes natural speaking style; extreme extremes (heavy shouting or extreme whispering) cannot be artificially forced without distorting voice timbre.

---
*Note: No profile is permanently locked. The final profile selection will be decided after listening.*