import sqlite3
from datetime import datetime

CANONICAL_SCRIPTS = [
    {
        'id': 'hps_ns_b1c01_gc0001_0003',
        'hook': 'Late at night, an old wizard in long robes appeared out of the shadows on Privet Drive.',
        'development': 'A stiff tabby cat sat motionless on a garden wall, watching him. Reaching into his cloak, Dumbledore pulled out a silver Deluminator and clicked it open, absorbing the streetlights into little balls of fire. One by one, the entire street fell pitch dark as he pocketed the lighter.',
        'payoff': "Looking down at the silent cat, Dumbledore smiled: 'I should have known you would be here, Professor McGonagall.'",
        'full_text': "Late at night, an old wizard in long robes appeared out of the shadows on Privet Drive. A stiff tabby cat sat motionless on a garden wall, watching him. Reaching into his cloak, Dumbledore pulled out a silver Deluminator and clicked it open, absorbing the streetlights into little balls of fire. One by one, the entire street fell pitch dark as he pocketed the lighter. Looking down at the silent cat, Dumbledore smiled: 'I should have known you would be here, Professor McGonagall.'"
    },
    {
        'id': 'hps_ns_b1c01_gc0004_0006',
        'hook': "The cat's shadow stretched along the brick wall, morphing into Professor McGonagall.",
        'development': 'Walking beside Dumbledore, she questioned the tragic rumors and pleaded against leaving Harry with the awful Dursleys. Dumbledore insisted Harry must grow up away from all the fame.',
        'payoff': 'Suddenly, a low mechanical roar shook the sky, and a flying motorcycle descended through the clouds, slamming down onto the pavement.',
        'full_text': "The cat's shadow stretched along the brick wall, morphing into Professor McGonagall. Walking beside Dumbledore, she questioned the tragic rumors and pleaded against leaving Harry with the awful Dursleys. Dumbledore insisted Harry must grow up away from all the fame. Suddenly, a low mechanical roar shook the sky, and a flying motorcycle descended through the clouds, slamming down onto the pavement."
    },
    {
        'id': 'hps_ns_b1c01_gc0007_0009',
        'hook': 'Stepping off the giant motorcycle onto Privet Drive, Hagrid took off his flying goggles and greeted the professors.',
        'development': 'In his massive arms, he gently cradled a bundle of blankets, explaining the baby had fallen asleep flying over Bristol. Handing the child to Dumbledore, the professors walked toward Number Four as McGonagall protested leaving Harry with Muggles.',
        'payoff': "Dumbledore looked down gently at the sleeping child: 'The only family he has.'",
        'full_text': "Stepping off the giant motorcycle onto Privet Drive, Hagrid took off his flying goggles and greeted the professors. In his massive arms, he gently cradled a bundle of blankets, explaining the baby had fallen asleep flying over Bristol. Handing the child to Dumbledore, the professors walked toward Number Four as McGonagall protested leaving Harry with Muggles. Dumbledore looked down gently at the sleeping child: 'The only family he has.'"
    },
    {
        'id': 'hps_ns_b1c01_gc0010_0012',
        'hook': "At the doorstep of Number Four Privet Drive, Dumbledore and McGonagall gazed down at baby Harry.",
        'development': 'McGonagall knew every child in their world would know his name. Dumbledore gently placed the sleeping baby on the front welcome mat and tucked a letter for Aunt Petunia into the blankets.',
        'payoff': "Whispering 'Good luck, Harry Potter,' Dumbledore clicked the streetlights back on as the camera zoomed into the lightning bolt scar.",
        'full_text': "At the doorstep of Number Four Privet Drive, Dumbledore and McGonagall gazed down at baby Harry. McGonagall knew every child in their world would know his name. Dumbledore gently placed the sleeping baby on the front welcome mat and tucked a letter for Aunt Petunia into the blankets. Whispering 'Good luck, Harry Potter,' Dumbledore clicked the streetlights back on as the camera zoomed into the lightning bolt scar."
    },
    {
        'id': 'hps_disc_peeves_poltergeist_b1',
        'hook': 'At the start-of-term feast, mountains of food magically appeared across the Great Hall tables.',
        'development': 'Suddenly, the ghost Nearly Headless Nick popped up through a platter, swinging his head aside on its severed neck to shock the first years.',
        'payoff': 'Leading them to their dormitory, Percy warned them about the massive stone staircases that shifted mid-air as living portraits welcomed them.',
        'full_text': 'At the start-of-term feast, mountains of food magically appeared across the Great Hall tables. Suddenly, the ghost Nearly Headless Nick popped up through a platter, swinging his head aside on its severed neck to shock the first years. Leading them to their dormitory, Percy warned them about the massive stone staircases that shifted mid-air as living portraits welcomed them.'
    },
    {
        'id': 'hps_disc_neville_hufflepuff_sorting_b1',
        'hook': 'During morning breakfast in the Great Hall, hundreds of post owls flooded through the high arched windows.',
        'development': 'A majestic owl swooped low, dropping a mysterious long parcel onto Harry\'s table. Tearing open the wrapping, Harry and Ron revealed the polished mahogany handle of the brand new Nimbus Two Thousand.',
        'payoff': 'Looking up, Harry caught Professor McGonagall smiling from the High Table, proving even strict rules could be bent for destiny.',
        'full_text': 'During morning breakfast in the Great Hall, hundreds of post owls flooded through the high arched windows. A majestic owl swooped low, dropping a mysterious long parcel onto Harry\'s table. Tearing open the wrapping, Harry and Ron revealed the polished mahogany handle of the brand new Nimbus Two Thousand. Looking up, Harry caught Professor McGonagall smiling from the High Table, proving even strict rules could be bent for destiny.'
    },
    {
        'id': 'hps_disc_mirror_of_erised_inscription_b1',
        'hook': 'Sneaking through dark corridors with a brass lantern, Harry discovered an abandoned classroom.',
        'development': 'Inside stood the towering Mirror of Erised, its golden frame carved with a backward inscription. Read in reverse, it revealed: \'I show not your face, but your heart\'s desire,\' as his parents appeared smiling beside him.',
        'payoff': 'Stepping from the shadows, Dumbledore reminded Harry that it does not do to dwell on dreams and forget to live.',
        'full_text': 'Sneaking through dark corridors with a brass lantern, Harry discovered an abandoned classroom. Inside stood the towering Mirror of Erised, its golden frame carved with a backward inscription. Read in reverse, it revealed: \'I show not your face, but your heart\'s desire,\' as his parents appeared smiling beside him. Stepping from the shadows, Dumbledore reminded Harry that it does not do to dwell on dreams and forget to live.'
    },
    {
        'id': 'hps_disc_neville_remembrall_cloak_b1',
        'hook': 'When morning mail arrived at breakfast, Neville Longbottom unwrapped a gift from his grandmother.',
        'development': 'It was a Remembrall, and the moment he touched it, the smoke flared bright red. Confused, Neville couldn\'t remember what he forgot.',
        'payoff': 'Look closely at the table: while every student wears black robes, Neville forgot his school robes!',
        'full_text': 'When morning mail arrived at breakfast, Neville Longbottom unwrapped a gift from his grandmother. It was a Remembrall, and the moment he touched it, the smoke flared bright red. Confused, Neville couldn\'t remember what he forgot. Look closely at the table: while every student wears black robes, Neville forgot his school robes!'
    }
]

def run():
    conn = sqlite3.connect('data/database/pipeline.db')
    c = conn.cursor()
    for item in CANONICAL_SCRIPTS:
        wcount = len(item['full_text'].split())
        dur = round(wcount / 2.8, 2)
        c.execute('''
            UPDATE hp_scripts
            SET hook = ?, development = ?, payoff = ?, full_text = ?, word_count = ?, estimated_duration_sec = ?, updated_at = ?
            WHERE id = ?
        ''', (item['hook'], item['development'], item['payoff'], item['full_text'], wcount, dur, datetime.utcnow(), item['id']))
        print(f"Updated {item['id']}: {wcount} words, ~{dur}s")
    conn.commit()
    conn.close()
    print("Database hp_scripts updated successfully.")

if __name__ == '__main__':
    run()
