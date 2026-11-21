import difflib
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.metrics.pairwise import linear_kernel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# saved by the notebook: {'df': movie table, 'features': sparse matrix (one row per movie)}
artifacts = joblib.load('traditional_model/recommender_artifacts.joblib')
df = artifacts['df'].reset_index(drop=True)
matrix = artifacts['features']

POP_WEIGHT = 0.25
titles_lower = df['title'].str.lower()
unique_titles = titles_lower.unique().tolist()
log_votes = np.log10(df['vote_count'].values)


class MovieRequest(BaseModel):
    title: str
    year: Optional[int] = None      # optional, to pick between movies with the same title
    n: int = Field(10, ge=1, le=30)


@app.get('/')
def root():
    return {'status': 'Movie recommender is live', 'movies': len(df)}


@app.get('/search')
def search(q: str, limit: int = 8):
    q = q.strip().lower()
    if len(q) < 2:
        return []
    hits = df.loc[titles_lower.str.contains(q, regex=False)]
    hits = hits.sort_values('vote_count', ascending=False).head(limit)
    return [{'title': t, 'year': None if pd.isna(y) else int(y)}
            for t, y in zip(hits['title'], hits['year'])]


@app.post('/recommend')
def recommend(request: MovieRequest):
    mask = titles_lower == request.title.lower()
    if request.year is not None:
        mask = mask & (df['year'] == request.year)
    matches = df.index[mask]

    if len(matches) == 0:
        close = difflib.get_close_matches(request.title.lower(), unique_titles, n=5, cutoff=0.6)
        raise HTTPException(status_code=404,
                            detail={'message': f'No exact match for "{request.title}"', 'suggestions': close})

    # same logic as the notebook
    idx = df.loc[matches, 'vote_count'].idxmax()
    sims = linear_kernel(matrix[idx], matrix).ravel()
    sims[df.index[titles_lower == request.title.lower()]] = -1      # never recommend the movie (or its namesakes) to itself

    candidates = np.argsort(sims)[::-1][:100]
    scores = sims[candidates] * (1 + POP_WEIGHT * log_votes[candidates])
    top = candidates[np.argsort(scores)[::-1][:request.n]]

    out = df.loc[top, ['title', 'year', 'genres', 'director', 'vote_average', 'vote_count']].copy()
    out['similarity'] = sims[top].round(3)
    out['year'] = out['year'].astype('Int64')
    out['vote_count'] = out['vote_count'].astype(int)
    out = out.astype(object).where(out.notna(), None)      # NaN is not valid JSON

    picked = df.loc[idx]
    return {
        'matched': {'title': picked['title'], 'year': None if pd.isna(picked['year']) else int(picked['year'])},
        'recommendations': out.to_dict('records'),
    }
