#!/usr/bin/env python3
"""
TMDB API'den otomatik dizi verisi toplama
Hedef: 500+ dizi
"""

import requests
import json
import time
import random
from typing import List, Dict
import os

class SeriesIngester:
    def __init__(self):
        self.api_key = os.getenv("TMDB_API_KEY", "")
        self.base_url = "https://api.themoviedb.org/3"
        self.series = []
        
        # Dizi türleri
        self.genres = [
            {"id": 18, "name": "Drama"},
            {"id": 35, "name": "Komedi"},
            {"id": 80, "name": "Suç"},
            {"id": 99, "name": "Belgesel"},
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
            {"id": 37, "name": "Western"},
            {"id": 10759, "name": "Aksiyon & Macera"},
            {"id": 10762, "name": "Çocuk"},
            {"id": 10763, "name": "Haber"},
            {"id": 10764, "name": "Reality"},
            {"id": 10765, "name": "Sci-Fi & Fantastik"},
            {"id": 10766, "name": "Sabun Operası"},
            {"id": 10767, "name": "Konuşma"},
            {"id": 10768, "name": "Savaş & Politika"}
        ]

    def search_series(self, genre_id: int, page: int = 1) -> List[Dict]:
        """TMDB API'den dizi ara"""
        url = f"{self.base_url}/discover/tv"
        params = {
            'api_key': self.api_key,
            'with_genres': genre_id,
            'page': page,
            'language': 'tr-TR,en-US',
            'sort_by': 'popularity.desc',
            'include_adult': False,
            'include_null_first_air_dates': False
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

    def get_series_details(self, series_id: int) -> Dict:
        """Dizi detaylarını al"""
        url = f"{self.base_url}/tv/{series_id}"
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
            print(f"Series Details Error: {e}")
            return {}

    def parse_series(self, series_data: Dict, details: Dict = None) -> Dict:
        """Dizi verisini parse et"""
        # Yaş uygunluğu
        adult = series_data.get('adult', False)
        yas_uygun = not adult
        
        # Tür belirleme
        genre_ids = series_data.get('genre_ids', [])
        tur = self.determine_genre(genre_ids)
        
        # Tema belirleme
        overview = series_data.get('overview', '')
        tema = self.extract_themes(overview, genre_ids)
        
        # Yaratıcı
        creator = "Bilinmeyen Yaratıcı"
        if details and 'created_by' in details and details['created_by']:
            creator = details['created_by'][0].get('name', 'Bilinmeyen Yaratıcı')
        
        # Yapımcı tarzı
        yapimci_tarzi = self.determine_creator_style(tur)
        
        # Neden
        neden = self.generate_reason(tur, tema)
        
        # Sezon sayısı
        seasons = details.get('number_of_seasons', 1) if details else 1
        
        return {
            'baslik': series_data.get('name', 'Bilinmeyen Dizi'),
            'yaratici': creator,
            'sezon': seasons,
            'tur': tur,
            'yas_uygun': yas_uygun,
            'tema': tema,
            'yapimci_tarzi': yapimci_tarzi,
            'neden': neden,
            'yil': series_data.get('first_air_date', '')[:4] if series_data.get('first_air_date') else '2000',
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
            if genre_id == 18:  # Drama
                themes.append('drama')
            elif genre_id == 35:  # Komedi
                themes.append('komedi')
            elif genre_id == 80:  # Suç
                themes.append('suç')
            elif genre_id == 10751:  # Aile
                themes.append('aile')
            elif genre_id == 14:  # Fantastik
                themes.append('fantastik')
            elif genre_id == 36:  # Tarih
                themes.append('tarih')
            elif genre_id == 27:  # Korku
                themes.append('korku')
            elif genre_id == 10402:  # Müzik
                themes.append('müzik')
            elif genre_id == 9648:  # Gizem
                themes.append('gizem')
            elif genre_id == 10749:  # Romantik
                themes.append('aşk')
            elif genre_id == 878:  # Bilim Kurgu
                themes.append('gelecek')
            elif genre_id == 53:  # Gerilim
                themes.append('gerilim')
            elif genre_id == 10759:  # Aksiyon & Macera
                themes.append('aksiyon')
        
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
        if 'aile' in overview_lower or 'family' in overview_lower:
            themes.append('aile')
        
        # En az 2 tema
        if len(themes) < 2:
            themes.extend(['hayat', 'insan'])
        
        return themes[:5]  # Max 5 tema

    def determine_creator_style(self, tur: str) -> str:
        """Türe göre yapımcı tarzı"""
        style_mapping = {
            'Drama': 'duygusal_drama',
            'Komedi': 'mizahi_komedi',
            'Suç': 'gercekci_suc',
            'Belgesel': 'bilgilendirici',
            'Aile': 'sicak_aile',
            'Fantastik': 'yaratici_fantastik',
            'Tarih': 'tarihsel_gercekci',
            'Korku': 'atmosferik_korku',
            'Müzik': 'muzikal_duyarli',
            'Gizem': 'suspense_gizem',
            'Romantik': 'duygusal_romantik',
            'Bilim Kurgu': 'vizyoner_scifi',
            'TV Film': 'televizyon_uyumlu',
            'Gerilim': 'psikolojik_gerilim',
            'Savaş': 'gercekci_savas',
            'Western': 'klasik_western',
            'Aksiyon & Macera': 'epik_aksiyon',
            'Çocuk': 'egitici_cocuk',
            'Haber': 'bilgilendirici_haber',
            'Reality': 'gercekci_reality',
            'Sci-Fi & Fantastik': 'bilimsel_fantastik',
            'Sabun Operası': 'dramatik_sabun',
            'Konuşma': 'interaktif_konusma',
            'Savaş & Politika': 'politik_savas'
        }
        return style_mapping.get(tur, 'modern')

    def generate_reason(self, tur: str, tema: List[str]) -> str:
        """Tür ve temaya göre neden oluştur"""
        reasons = {
            'Drama': f"{' ve '.join(tema)} temalı duygusal drama serisi",
            'Komedi': f"{' ve '.join(tema)} konulu eğlenceli komedi",
            'Suç': f"{' ve '.join(tema)} temalı gerçekçi suç hikayesi",
            'Belgesel': f"{' ve '.join(tema)} konusunda bilgilendirici belgesel",
            'Aile': f"{' ve '.join(tema)} konulu sıcak aile dizisi",
            'Fantastik': f"{' ve '.join(tema)} temalı yaratıcı fantastik dünya",
            'Tarih': f"{' ve '.join(tema)} konusunda tarihi gerçeklik",
            'Korku': f"{' ve '.join(tema)} temalı atmosferik korku",
            'Müzik': f"{' ve '.join(tema)} konulu müziksel deneyim",
            'Gizem': f"{' ve '.join(tema)} gizemini çözen suspense",
            'Romantik': f"{' ve '.join(tema)} temalı duygusal aşk hikayesi",
            'Bilim Kurgu': f"{' ve '.join(tema)} konusunda vizyoner gelecek",
            'TV Film': f"{' ve '.join(tema)} temalı televizyon uyumlu dizi",
            'Gerilim': f"{' ve '.join(tema)} konulu psikolojik gerilim",
            'Savaş': f"{' ve '.join(tema)} temalı gerçekçi savaş anlatımı",
            'Western': f"{' ve '.join(tema)} konulu klasik western",
            'Aksiyon & Macera': f"{' ve '.join(tema)} temalı epik aksiyon",
            'Çocuk': f"{' ve '.join(tema)} konulu eğitici çocuk programı",
            'Haber': f"{' ve '.join(tema)} konusunda bilgilendirici haber",
            'Reality': f"{' ve '.join(tema)} temalı gerçekçi reality",
            'Sci-Fi & Fantastik': f"{' ve '.join(tema)} konulu bilimsel fantastik",
            'Sabun Operası': f"{' ve '.join(tema)} temalı dramatik sabun operası",
            'Konuşma': f"{' ve '.join(tema)} konulu interaktif konuşma programı",
            'Savaş & Politika': f"{' ve '.join(tema)} temalı politik savaş"
        }
        return reasons.get(tur, f"{' ve '.join(tema)} konulu ilginç dizi")

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

    def ingest_series(self, target_count: int = 500):
        """Ana ingestion fonksiyonu"""
        print(f"Dizi verisi toplama başlıyor... Hedef: {target_count}")
        
        # Türlere göre arama
        for genre in self.genres:
            if len(self.series) >= target_count:
                break
                
            print(f"{genre['name']} türünde dizi aranıyor...")
            
            # Her türden 30 dizi al
            for page in range(1, 4):  # 3 sayfa = 90 dizi
                if len(self.series) >= target_count:
                    break
                    
                series_list = self.search_series(genre['id'], page)
                
                for series in series_list:
                    if len(self.series) >= target_count:
                        break
                        
                    # Dizi detaylarını al
                    details = self.get_series_details(series['id'])
                    
                    parsed_series = self.parse_series(series, details)
                    if parsed_series['baslik'] not in [s['baslik'] for s in self.series]:
                        self.series.append(parsed_series)
                
                # API limit aşımını önle
                time.sleep(0.5)
        
        print(f"Toplam {len(self.series)} dizi toplandı!")
        return self.series

    def save_to_json(self, filename: str = '../data/series.json'):
        """JSON dosyasına kaydet"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.series, f, ensure_ascii=False, indent=2)
        print(f"Diziler {filename} dosyasına kaydedildi!")

def main():
    ingester = SeriesIngester()
    series = ingester.ingest_series(500)
    ingester.save_to_json()
    
    # İstatistikler
    genres = {}
    for series_item in series:
        genre = series_item['tur']
        genres[genre] = genres.get(genre, 0) + 1
    
    print("\nTür dağılımı:")
    for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True):
        print(f"{genre}: {count}")

if __name__ == "__main__":
    main()
