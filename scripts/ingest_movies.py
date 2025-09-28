#!/usr/bin/env python3
"""
TMDB API'den otomatik film verisi toplama
Hedef: 500+ film
"""

import requests
import json
import time
import random
from typing import List, Dict
import os

class MovieIngester:
    def __init__(self):
        self.api_key = os.getenv("TMDB_API_KEY", "")
        self.base_url = "https://api.themoviedb.org/3"
        self.movies = []
        
        # Film türleri
        self.genres = [
            {"id": 28, "name": "Aksiyon"},
            {"id": 12, "name": "Macera"},
            {"id": 16, "name": "Animasyon"},
            {"id": 35, "name": "Komedi"},
            {"id": 80, "name": "Suç"},
            {"id": 99, "name": "Belgesel"},
            {"id": 18, "name": "Drama"},
            {"id": 10751, "name": "Aile"},
            {"id": 14, "name": "Fantastik"},
            {"id": 36, "name": "Tarih"},
            {"id": 27, "name": "Korku"},
            {"id": 10402, "name": "Müzik"},
            {"id": 9648, "name": "Gizem"},
            {"id": 10749, "name": "Romantik"},
            {"id": 878, "name": "Bilim Kurgu"},
            {"id": 10770, "name": "TV Film"},
            {"id": 53, "name": "Gerilim"},
            {"id": 10752, "name": "Savaş"},
            {"id": 37, "name": "Western"}
        ]

    def search_movies(self, genre_id: int, page: int = 1) -> List[Dict]:
        """TMDB API'den film ara"""
        url = f"{self.base_url}/discover/movie"
        params = {
            'api_key': self.api_key,
            'with_genres': genre_id,
            'page': page,
            'language': 'tr-TR,en-US',
            'sort_by': 'popularity.desc',
            'include_adult': False
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])
            else:
                print(f"API Error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Request Error: {e}")
            return []

    def get_movie_details(self, movie_id: int) -> Dict:
        """Film detaylarını al"""
        url = f"{self.base_url}/movie/{movie_id}"
        params = {
            'api_key': self.api_key,
            'language': 'tr-TR',
            'append_to_response': 'credits,keywords'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                return {}
        except Exception as e:
            print(f"Movie Details Error: {e}")
            return {}

    def parse_movie(self, movie_data: Dict, details: Dict = None) -> Dict:
        """Film verisini parse et"""
        # Yaş uygunluğu
        adult = movie_data.get('adult', False)
        yas_uygun = not adult
        
        # Tür belirleme
        genre_ids = movie_data.get('genre_ids', [])
        tur = self.determine_genre(genre_ids)
        
        # Tema belirleme
        overview = movie_data.get('overview', '')
        tema = self.extract_themes(overview, genre_ids)
        
        # Yönetmen
        director = "Bilinmeyen Yönetmen"
        if details and 'credits' in details:
            crew = details['credits'].get('crew', [])
            for person in crew:
                if person.get('job') == 'Director':
                    director = person.get('name', 'Bilinmeyen Yönetmen')
                    break
        
        # Yönetmen tarzı
        yonetmen_tarzi = self.determine_director_style(tur)
        
        # Neden
        neden = self.generate_reason(tur, tema)
        
        return {
            'baslik': movie_data.get('title', 'Bilinmeyen Film'),
            'yonetmen': director,
            'dakika': movie_data.get('runtime', random.randint(90, 150)),
            'tur': tur,
            'yas_uygun': yas_uygun,
            'tema': tema,
            'yonetmen_tarzi': yonetmen_tarzi,
            'neden': neden,
            'yil': movie_data.get('release_date', '')[:4] if movie_data.get('release_date') else '2000',
            'aciklama': overview[:200] if overview else '',
            'anahtar_kelimeler': self.extract_keywords(overview, genre_ids)
        }

    def determine_genre(self, genre_ids: List[int]) -> str:
        """Genre ID'lerine göre tür belirle"""
        if not genre_ids:
            return 'Drama'
        
        # İlk genre'ü al
        first_genre_id = genre_ids[0]
        
        for genre in self.genres:
            if genre['id'] == first_genre_id:
                return genre['name']
        
        return 'Drama'

    def extract_themes(self, overview: str, genre_ids: List[int]) -> List[str]:
        """Açıklamadan tema çıkar"""
        themes = []
        
        # Genre'lardan tema
        for genre_id in genre_ids:
            if genre_id == 28:  # Aksiyon
                themes.append('aksiyon')
            elif genre_id == 12:  # Macera
                themes.append('macera')
            elif genre_id == 35:  # Komedi
                themes.append('komedi')
            elif genre_id == 18:  # Drama
                themes.append('drama')
            elif genre_id == 10749:  # Romantik
                themes.append('aşk')
            elif genre_id == 878:  # Bilim Kurgu
                themes.append('gelecek')
            elif genre_id == 14:  # Fantastik
                themes.append('fantastik')
            elif genre_id == 27:  # Korku
                themes.append('korku')
            elif genre_id == 53:  # Gerilim
                themes.append('gerilim')
        
        # Açıklamadan tema
        overview_lower = overview.lower()
        if 'aşk' in overview_lower or 'love' in overview_lower:
            themes.append('aşk')
        if 'macera' in overview_lower or 'adventure' in overview_lower:
            themes.append('macera')
        if 'aksiyon' in overview_lower or 'action' in overview_lower:
            themes.append('aksiyon')
        if 'gizem' in overview_lower or 'mystery' in overview_lower:
            themes.append('gizem')
        if 'tarih' in overview_lower or 'history' in overview_lower:
            themes.append('tarih')
        
        # En az 2 tema
        if len(themes) < 2:
            themes.extend(['hayat', 'insan'])
        
        return themes[:5]  # Max 5 tema

    def determine_director_style(self, tur: str) -> str:
        """Türe göre yönetmen tarzı"""
        style_mapping = {
            'Aksiyon': 'gorsel_aksiyon',
            'Macera': 'epik_macera',
            'Animasyon': 'yaratici_animasyon',
            'Komedi': 'mizahi_komedi',
            'Suç': 'gercekci_suc',
            'Belgesel': 'bilgilendirici',
            'Drama': 'duygusal_drama',
            'Aile': 'sıcak_aile',
            'Fantastik': 'yaratici_fantastik',
            'Tarih': 'tarihsel_gercekci',
            'Korku': 'atmosferik_korku',
            'Müzik': 'muzikal_duyarlı',
            'Gizem': 'suspense_gizem',
            'Romantik': 'duygusal_romantik',
            'Bilim Kurgu': 'vizyoner_scifi',
            'TV Film': 'televizyon_uyumlu',
            'Gerilim': 'psikolojik_gerilim',
            'Savaş': 'gercekci_savas',
            'Western': 'klasik_western'
        }
        return style_mapping.get(tur, 'modern')

    def generate_reason(self, tur: str, tema: List[str]) -> str:
        """Tür ve temaya göre neden oluştur"""
        reasons = {
            'Aksiyon': f"{' ve '.join(tema)} temalı nefes kesen aksiyon",
            'Macera': f"{' ve '.join(tema)} konulu büyük macera",
            'Animasyon': f"{' ve '.join(tema)} temalı yaratıcı animasyon",
            'Komedi': f"{' ve '.join(tema)} konulu eğlenceli komedi",
            'Suç': f"{' ve '.join(tema)} temalı gerçekçi suç hikayesi",
            'Belgesel': f"{' ve '.join(tema)} konusunda bilgilendirici belgesel",
            'Drama': f"{' ve '.join(tema)} temalı duygusal drama",
            'Aile': f"{' ve '.join(tema)} konulu sıcak aile filmi",
            'Fantastik': f"{' ve '.join(tema)} temalı yaratıcı fantastik dünya",
            'Tarih': f"{' ve '.join(tema)} konusunda tarihi gerçeklik",
            'Korku': f"{' ve '.join(tema)} temalı atmosferik korku",
            'Müzik': f"{' ve '.join(tema)} konulu müziksel deneyim",
            'Gizem': f"{' ve '.join(tema)} gizemini çözen suspense",
            'Romantik': f"{' ve '.join(tema)} temalı duygusal aşk hikayesi",
            'Bilim Kurgu': f"{' ve '.join(tema)} konusunda vizyoner gelecek",
            'TV Film': f"{' ve '.join(tema)} temalı televizyon uyumlu film",
            'Gerilim': f"{' ve '.join(tema)} konulu psikolojik gerilim",
            'Savaş': f"{' ve '.join(tema)} temalı gerçekçi savaş anlatımı",
            'Western': f"{' ve '.join(tema)} konulu klasik western"
        }
        return reasons.get(tur, f"{' ve '.join(tema)} konulu ilginç film")

    def extract_keywords(self, overview: str, genre_ids: List[int]) -> List[str]:
        """Anahtar kelimeler çıkar"""
        keywords = []
        
        # Genre'lardan
        for genre_id in genre_ids:
            for genre in self.genres:
                if genre['id'] == genre_id:
                    keywords.extend(genre['name'].lower().split())
                    break
        
        # Açıklamadan
        if overview:
            overview_words = overview.lower().split()
            keywords.extend([w for w in overview_words if len(w) > 3])
        
        return list(set(keywords))[:10]  # Max 10 anahtar kelime

    def ingest_movies(self, target_count: int = 500):
        """Ana ingestion fonksiyonu"""
        print(f"Film verisi toplama başlıyor... Hedef: {target_count}")
        
        # Türlere göre arama
        for genre in self.genres:
            if len(self.movies) >= target_count:
                break
                
            print(f"{genre['name']} türünde film aranıyor...")
            
            # Her türden 30 film al
            for page in range(1, 4):  # 3 sayfa = 90 film
                if len(self.movies) >= target_count:
                    break
                    
                movies = self.search_movies(genre['id'], page)
                
                for movie in movies:
                    if len(self.movies) >= target_count:
                        break
                        
                    # Film detaylarını al
                    details = self.get_movie_details(movie['id'])
                    
                    parsed_movie = self.parse_movie(movie, details)
                    if parsed_movie['baslik'] not in [m['baslik'] for m in self.movies]:
                        self.movies.append(parsed_movie)
                
                # API limit aşımını önle
                time.sleep(0.5)
        
        print(f"Toplam {len(self.movies)} film toplandı!")
        return self.movies

    def save_to_json(self, filename: str = '../data/movies.json'):
        """JSON dosyasına kaydet"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.movies, f, ensure_ascii=False, indent=2)
        print(f"Filmler {filename} dosyasına kaydedildi!")

def main():
    ingester = MovieIngester()
    movies = ingester.ingest_movies(500)
    ingester.save_to_json()
    
    # İstatistikler
    genres = {}
    for movie in movies:
        genre = movie['tur']
        genres[genre] = genres.get(genre, 0) + 1
    
    print("\nTür dağılımı:")
    for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True):
        print(f"{genre}: {count}")

if __name__ == "__main__":
    main()
