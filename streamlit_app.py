import os

import pandas as pd
import requests
import streamlit as st

# local by default; after deploying, set API_URL to your Render URL (env variable or Streamlit secret)
API_URL = os.getenv('API_URL', 'http://127.0.0.1:8000')

st.set_page_config(page_title='Movie Recommender', page_icon='🎬')
st.title('🎬 Movie Recommender')
st.write('Search for a movie you like and get similar ones.')

query = st.text_input('Search for a movie', placeholder='e.g. Inception')
n = st.slider('How many recommendations?', 1, 10, 5)

try:
    movie = None
    if query:
        response = requests.get(f'{API_URL}/search', params={'q': query}, timeout=30)
        response.raise_for_status()
        matches = response.json()

        if matches:
            labels = [f"{m['title']} ({m['year'] or 'n/a'})" for m in matches]
            choice = st.selectbox('Pick the exact movie', labels)
            movie = matches[labels.index(choice)]
        else:
            st.warning('No movie found with that name. Try a different spelling or fewer words.')

    if movie and st.button('Recommend'):
        response = requests.post(
            f'{API_URL}/recommend',
            json={'title': movie['title'], 'year': movie['year'], 'n': n},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        recs = pd.DataFrame(result['recommendations'])
        recs['year'] = recs['year'].astype('Int64')
        recs['genres'] = recs['genres'].str.replace(r'[|-]', ', ', regex=True)
        recs['director'] = recs['director'].fillna('').replace('', '—')
        recs = recs.rename(columns={
            'title': 'Title', 'year': 'Year', 'genres': 'Genres', 'director': 'Director',
            'vote_average': 'Rating', 'vote_count': 'Votes', 'similarity': 'Match'
        })

        st.success(f"Movies similar to {result['matched']['title']} ({result['matched']['year'] or 'n/a'})")
        st.dataframe(
            recs,
            hide_index=True,
            width='stretch',
            column_config={'Match': st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format='%.2f')}
        )
except requests.exceptions.Timeout:
    st.warning('⏳ The API is waking up (free tier cold start). Wait 10 seconds and try again.')
except requests.exceptions.ConnectionError:
    st.error('🔌 Could not reach the API. Check your internet or Render deployment status.')
except Exception as e:
    st.error(f'Something went wrong: {e}')