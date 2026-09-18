import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH
from core.models import MovieAssetRecord, MovieSubtitleChunk
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(f"sqlite:///{DB_PATH}")
Session = sessionmaker(bind=engine)

with Session() as session:
    assets = session.query(MovieAssetRecord).order_by(MovieAssetRecord.movie_number.asc()).all()
    print(f"Total MovieAssetRecords in DB: {len(assets)}")
    for a in assets:
        sub_count = session.query(MovieSubtitleChunk).filter_by(movie_number=a.movie_number).count()
        print(f"Movie {a.movie_number}: '{a.title}' | Video: {a.video_filename} | SRT: {a.srt_filename} | Chunks: {sub_count}")
