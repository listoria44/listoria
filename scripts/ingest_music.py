#!/usr/bin/env python3
"""
Last.fm ve Spotify API'den otomatik müzik verisi toplama
Hedef: 2000+ şarkı
"""

import requests
import json
import time
import random
from typing import List, Dict
import os

class MusicIngester:
    def __init__(self):
        self.lastfm_api_key = os.getenv("LASTFM_API_KEY", "")
        self.spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self.music = []
        
        # Müzik türleri
        self.genres = [
            "pop", "rock", "hip-hop", "electronic", "jazz", "classical",
            "country", "r&b", "folk", "blues", "reggae", "punk",
            "metal", "indie", "alternative", "dance", "house", "techno"
        ]
        
        # Türkçe sanatçılar
        self.turkish_artists = [
            "Tarkan", "Sezen Aksu", "Barış Manço", "Cem Karaca", "Teoman",
            "Sıla", "Hadise", "Ezhel", "Ceza", "Şanışer", "Neşet Ertaş",
            "Zeki Müren", "Ajda Pekkan", "Emel Sayın", "Nilüfer"
        ]

    def search_lastfm_tracks(self, genre: str, limit: int = 50) -> List[Dict]:
        """Last.fm API'den şarkı ara"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params = {
            'method': 'tag.gettoptracks',
            'tag': genre,
            'api_key': self.lastfm_api_key,
            'format': 'json',
            'limit': limit
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                tracks = data.get('toptracks', {}).get('track', [])
                return tracks
            else:
                print(f"Last.fm API Error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Last.fm Request Error: {e}")
            return []

    def get_track_info(self, artist: str, track: str) -> Dict:
        """Şarkı detaylarını al"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params = {
            'method': 'track.getinfo',
            'artist': artist,
            'track': track,
            'api_key': self.lastfm_api_key,
            'format': 'json'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get('track', {})
            else:
                return {}
        except Exception as e:
            print(f"Track Info Error: {e}")
            return {}

    def parse_track(self, track_data: Dict, track_info: Dict = None) -> Dict:
        """Şarkı verisini parse et"""
        # Yaş uygunluğu (basit kontrol)
        yas_uygun = True  # Müzik genelde uygun
        
        # Tür belirleme
        tags = track_info.get('toptags', {}).get('tag', []) if track_info else []
        tur = self.determine_genre(tags)
        
        # Tema belirleme
        tags_text = ' '.join([tag.get('name', '') for tag in tags])
        tema = self.extract_themes(tags_text, tur)
        
        # Sanatçı tarzı
        sanatci_tarzi = self.determine_artist_style(tur)
        
        # Neden
        neden = self.generate_reason(tur, tema)
        
        # Dil belirleme
        artist = track_data.get('artist', {}).get('name', 'Bilinmeyen Sanatçı')
        dil = self.determine_language(artist)
        
        return {
            'baslik': track_data.get('name', 'Bilinmeyen Şarkı'),
            'sanatci': artist,
            'tur': tur,
            'dil': dil,
            'yil': track_data.get('year', '2000') if track_data.get('year') else '2000',
            'tema': tema,
            'sanatci_tarzi': sanatci_tarzi,
            'yas_uygun': yas_uygun,
            'neden': neden,
            'album': track_data.get('album', {}).get('name', '') if track_data.get('album') else '',
            'anahtar_kelimeler': self.extract_keywords(tags_text, tur)
        }

    def determine_genre(self, tags: List[Dict]) -> str:
        """Tag'lere göre tür belirle"""
        if not tags:
            return 'Pop'
        
        # Tag'leri küçük harfe çevir
        tag_names = [tag.get('name', '').lower() for tag in tags]
        
        genre_mapping = {
            'pop': 'Pop',
            'rock': 'Rock',
            'hip-hop': 'Hip Hop',
            'electronic': 'Electronic',
            'jazz': 'Jazz',
            'classical': 'Klasik',
            'country': 'Country',
            'r&b': 'R&B',
            'folk': 'Folk',
            'blues': 'Blues',
            'reggae': 'Reggae',
            'punk': 'Punk',
            'metal': 'Metal',
            'indie': 'Indie',
            'alternative': 'Alternative',
            'dance': 'Dance',
            'house': 'House',
            'techno': 'Techno'
        }
        
        for eng, tr in genre_mapping.items():
            if eng in tag_names:
                return tr
        
        return 'Pop'

    def extract_themes(self, tags_text: str, tur: str) -> List[str]:
        """Tag'lerden tema çıkar"""
        themes = []
        tags_lower = tags_text.lower()
        
        # Tür bazlı tema
        if tur == 'Pop':
            themes.extend(['aşk', 'hayat', 'eğlence'])
        elif tur == 'Rock':
            themes.extend(['isyan', 'güç', 'enerji'])
        elif tur == 'Hip Hop':
            themes.extend(['sokak', 'gerçek', 'güçlü'])
        elif tur == 'Electronic':
            themes.extend(['dans', 'ritim', 'gelecek'])
        elif tur == 'Jazz':
            themes.extend(['müzik', 'ritim', 'sakin'])
        elif tur == 'Klasik':
            themes.extend(['müzik', 'sanat', 'zaman'])
        
        # Tag'lerden tema
        if 'love' in tags_lower or 'aşk' in tags_lower:
            themes.append('aşk')
        if 'dance' in tags_lower or 'dans' in tags_lower:
            themes.append('dans')
        if 'sad' in tags_lower or 'üzgün' in tags_lower:
            themes.append('melankolik')
        if 'happy' in tags_lower or 'mutlu' in tags_lower:
            themes.append('neşeli')
        if 'party' in tags_lower or 'parti' in tags_lower:
            themes.append('eğlence')
        
        # En az 2 tema
        if len(themes) < 2:
            themes.extend(['müzik', 'ritim'])
        
        return themes[:5]  # Max 5 tema

    def determine_artist_style(self, tur: str) -> str:
        """Türe göre sanatçı tarzı"""
        style_mapping = {
            'Pop': 'pop_star',
            'Rock': 'rock_star',
            'Hip Hop': 'rap_artist',
            'Electronic': 'electronic_producer',
            'Jazz': 'jazz_musician',
            'Klasik': 'classical_composer',
            'Country': 'country_singer',
            'R&B': 'rnb_artist',
            'Folk': 'folk_singer',
            'Blues': 'blues_musician',
            'Reggae': 'reggae_artist',
            'Punk': 'punk_artist',
            'Metal': 'metal_artist',
            'Indie': 'indie_artist',
            'Alternative': 'alternative_artist',
            'Dance': 'dance_artist',
            'House': 'house_producer',
            'Techno': 'techno_producer'
        }
        return style_mapping.get(tur, 'modern_artist')

    def generate_reason(self, tur: str, tema: List[str]) -> str:
        """Tür ve temaya göre neden oluştur"""
        reasons = {
            'Pop': f"{' ve '.join(tema)} temalı pop müziğin en iyi örnekleri",
            'Rock': f"{' ve '.join(tema)} konulu güçlü rock enerjisi",
            'Hip Hop': f"{' ve '.join(tema)} temalı gerçekçi hip hop",
            'Electronic': f"{' ve '.join(tema)} konulu elektronik dans müziği",
            'Jazz': f"{' ve '.join(tema)} temalı sofistike jazz ritimleri",
            'Klasik': f"{' ve '.join(tema)} konulu zamansız klasik müzik",
            'Country': f"{' ve '.join(tema)} temalı samimi country hikayeleri",
            'R&B': f"{' ve '.join(tema)} konulu duygusal R&B",
            'Folk': f"{' ve '.join(tema)} temalı geleneksel folk müziği",
            'Blues': f"{' ve '.join(tema)} konulu derin blues duyguları",
            'Reggae': f"{' ve '.join(tema)} temalı rahatlatıcı reggae",
            'Punk': f"{' ve '.join(tema)} konulu isyankar punk enerjisi",
            'Metal': f"{' ve '.join(tema)} temalı güçlü metal gücü",
            'Indie': f"{' ve '.join(tema)} konulu bağımsız indie müzik",
            'Alternative': f"{' ve '.join(tema)} temalı alternatif yaklaşım",
            'Dance': f"{' ve '.join(tema)} konulu dans edilebilir ritimler",
            'House': f"{' ve '.join(tema)} temalı ev müziği ritimleri",
            'Techno': f"{' ve '.join(tema)} konulu teknolojik techno"
        }
        return reasons.get(tur, f"{' ve '.join(tema)} konulu ilginç müzik")

    def determine_language(self, artist: str) -> str:
        """Sanatçıya göre dil belirleme"""
        artist_lower = artist.lower()
        
        # Türkçe sanatçılar
        for tr_artist in self.turkish_artists:
            if tr_artist.lower() in artist_lower:
                return 'Türkçe'
        
        # Yaygın İngilizce sanatçılar
        english_artists = ['queen', 'beatles', 'michael jackson', 'madonna', 'beyonce']
        for eng_artist in english_artists:
            if eng_artist in artist_lower:
                return 'İngilizce'
        
        # Varsayılan İngilizce
        return 'İngilizce'

    def extract_keywords(self, tags_text: str, tur: str) -> List[str]:
        """Anahtar kelimeler çıkar"""
        keywords = []
        
        # Tag'lerden
        if tags_text:
            tag_words = tags_text.lower().split()
            keywords.extend([w for w in tag_words if len(w) > 3])
        
        # Türden
        keywords.extend(tur.lower().split())
        
        return list(set(keywords))[:10]  # Max 10 anahtar kelime

    def ingest_music(self, target_count: int = 2000):
        """Ana ingestion fonksiyonu"""
        print(f"Müzik verisi toplama başlıyor... Hedef: {target_count}")
        
        # Türlere göre arama
        for genre in self.genres:
            if len(self.music) >= target_count:
                break
                
            print(f"{genre} türünde müzik aranıyor...")
            
            # Her türden 100+ şarkı al
            tracks = self.search_lastfm_tracks(genre, 100)
            
            for track in tracks:
                if len(self.music) >= target_count:
                    break
                    
                # Şarkı detaylarını al
                track_info = self.get_track_info(
                    track['artist']['name'], 
                    track['name']
                )
                
                parsed_track = self.parse_track(track, track_info)
                if parsed_track['baslik'] not in [m['baslik'] for m in self.music]:
                    self.music.append(parsed_track)
                
                # API limit aşımını önle
                time.sleep(0.1)
        
        print(f"Toplam {len(self.music)} şarkı toplandı!")
        return self.music

    def save_to_json(self, filename: str = '../data/music.json'):
        """JSON dosyasına kaydet"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.music, f, ensure_ascii=False, indent=2)
        print(f"Müzik {filename} dosyasına kaydedildi!")

def main():
    ingester = MusicIngester()
    music = ingester.ingest_music(2000)
    ingester.save_to_json()
    
    # İstatistikler
    genres = {}
    languages = {}
    for track in music:
        genre = track['tur']
        language = track['dil']
        genres[genre] = genres.get(genre, 0) + 1
        languages[language] = languages.get(language, 0) + 1
    
    print("\nTür dağılımı:")
    for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True):
        print(f"{genre}: {count}")
    
    print("\nDil dağılımı:")
    for language, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
        print(f"{language}: {count}")

if __name__ == "__main__":
    main()
