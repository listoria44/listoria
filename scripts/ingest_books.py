#!/usr/bin/env python3
"""
Google Books API'den otomatik kitap verisi toplama
Hedef: 1000+ kitap
"""

import requests
import json
import time
import random
from typing import List, Dict
import os

class BookIngester:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_BOOKS_API_KEY", "")
        self.base_url = "https://www.googleapis.com/books/v1/volumes"
        self.books = []
        
        # Türkçe ve İngilizce türler
        self.genres = [
            "fantasy", "science fiction", "romance", "mystery", "thriller",
            "biography", "history", "philosophy", "self-help", "business",
            "cooking", "travel", "poetry", "drama", "comedy"
        ]
        
        # Türkçe anahtar kelimeler
        self.turkish_keywords = [
            "türk", "istanbul", "ankara", "izmir", "türkiye", "osmanlı",
            "atatürk", "türkçe", "anadolu", "trakya", "karadeniz", "ege"
        ]

    def search_books(self, query: str, max_results: int = 40) -> List[Dict]:
        """Google Books API'den kitap ara"""
        params = {
            'q': query,
            'key': self.api_key,
            'maxResults': max_results,
            'langRestrict': 'tr,en'
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get('items', [])
            else:
                print(f"API Error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Request Error: {e}")
            return []

    def parse_book(self, book_data: Dict) -> Dict:
        """Kitap verisini parse et"""
        volume_info = book_data.get('volumeInfo', {})
        
        # Sayfa sayısı
        page_count = volume_info.get('pageCount', 0)
        if not page_count:
            page_count = random.randint(200, 800)
        
        # Yaş uygunluğu (basit kontrol)
        content_rating = volume_info.get('maturityRating', 'NOT_MATURE')
        yas_uygun = content_rating == 'NOT_MATURE'
        
        # Tür belirleme
        categories = volume_info.get('categories', [])
        tur = self.determine_genre(categories)
        
        # Tema belirleme
        description = volume_info.get('description', '')
        tema = self.extract_themes(description, categories)
        
        return {
            'baslik': volume_info.get('title', 'Bilinmeyen Kitap'),
            'yazar': ', '.join(volume_info.get('authors', ['Bilinmeyen Yazar'])),
            'sayfa': page_count,
            'tur': tur,
            'yas_uygun': yas_uygun,
            'tema': tema,
            'yazar_tarzi': self.determine_author_style(tur),
            'neden': self.generate_reason(tur, tema),
            'dil': self.determine_language(volume_info),
            'yil': volume_info.get('publishedDate', '')[:4] if volume_info.get('publishedDate') else '2000',
            'aciklama': description[:200] if description else '',
            'anahtar_kelimeler': self.extract_keywords(description, categories)
        }

    def determine_genre(self, categories: List[str]) -> str:
        """Kategoriye göre tür belirle"""
        if not categories:
            return random.choice(['Modern', 'Klasik', 'Popüler'])
        
        category_lower = ' '.join(categories).lower()
        
        genre_mapping = {
            'fantasy': 'Fantastik',
            'science fiction': 'Bilim Kurgu',
            'romance': 'Romantik',
            'mystery': 'Gizem',
            'thriller': 'Gerilim',
            'biography': 'Biyografi',
            'history': 'Tarih',
            'philosophy': 'Felsefe',
            'self-help': 'Kişisel Gelişim',
            'business': 'İş',
            'cooking': 'Yemek',
            'travel': 'Seyahat',
            'poetry': 'Şiir',
            'drama': 'Drama',
            'comedy': 'Komedi'
        }
        
        for eng, tr in genre_mapping.items():
            if eng in category_lower:
                return tr
        
        return 'Modern'

    def extract_themes(self, description: str, categories: List[str]) -> List[str]:
        """Açıklamadan tema çıkar"""
        themes = []
        
        # Kategorilerden tema
        for category in categories:
            if category.lower() in ['romance', 'love']:
                themes.append('aşk')
            elif category.lower() in ['adventure', 'action']:
                themes.append('macera')
            elif category.lower() in ['mystery', 'crime']:
                themes.append('gizem')
            elif category.lower() in ['fantasy', 'magic']:
                themes.append('büyü')
        
        # Açıklamadan tema
        desc_lower = description.lower()
        if 'aşk' in desc_lower or 'love' in desc_lower:
            themes.append('aşk')
        if 'macera' in desc_lower or 'adventure' in desc_lower:
            themes.append('macera')
        if 'gizem' in desc_lower or 'mystery' in desc_lower:
            themes.append('gizem')
        if 'tarih' in desc_lower or 'history' in desc_lower:
            themes.append('tarih')
        
        # En az 2 tema
        if len(themes) < 2:
            themes.extend(['hayat', 'insan'])
        
        return themes[:5]  # Max 5 tema

    def determine_author_style(self, tur: str) -> str:
        """Türe göre yazar tarzı"""
        style_mapping = {
            'Fantastik': 'modern_fantastik',
            'Bilim Kurgu': 'hard_scifi',
            'Romantik': 'modern_romantik',
            'Gizem': 'polisiye',
            'Gerilim': 'psikolojik_gerilim',
            'Biyografi': 'biyografik',
            'Tarih': 'tarihsel',
            'Felsefe': 'felsefi',
            'Kişisel Gelişim': 'motivasyonel',
            'İş': 'profesyonel',
            'Yemek': 'pratik',
            'Seyahat': 'seyahat',
            'Şiir': 'modern_şiir',
            'Drama': 'duygusal_drama',
            'Komedi': 'mizahi'
        }
        return style_mapping.get(tur, 'modern')

    def generate_reason(self, tur: str, tema: List[str]) -> str:
        """Tür ve temaya göre neden oluştur"""
        reasons = {
            'Fantastik': f"{' ve '.join(tema)} temalı fantastik dünya",
            'Bilim Kurgu': f"Gelecekte {' ve '.join(tema)} konuları",
            'Romantik': f"{' ve '.join(tema)} temalı aşk hikayesi",
            'Gizem': f"{' ve '.join(tema)} gizemini çözen hikaye",
            'Gerilim': f"{' ve '.join(tema)} konulu gerilim dolu anlatım",
            'Biyografi': f"{' ve '.join(tema)} konulu ilham verici hayat hikayesi",
            'Tarih': f"{' ve '.join(tema)} konulu tarihi anlatım",
            'Felsefe': f"{' ve '.join(tema)} üzerine derin düşünceler",
            'Kişisel Gelişim': f"{' ve '.join(tema)} konusunda kişisel gelişim",
            'İş': f"{' ve '.join(tema)} konusunda profesyonel rehber",
            'Yemek': f"{' ve '.join(tema)} temalı pratik tarifler",
            'Seyahat': f"{' ve '.join(tema)} konulu seyahat deneyimleri",
            'Şiir': f"{' ve '.join(tema)} temalı duygusal şiirler",
            'Drama': f"{' ve '.join(tema)} konulu duygusal drama",
            'Komedi': f"{' ve '.join(tema)} temalı mizahi anlatım"
        }
        return reasons.get(tur, f"{' ve '.join(tema)} konulu ilginç hikaye")

    def determine_language(self, volume_info: Dict) -> str:
        """Dil belirleme"""
        language = volume_info.get('language', 'en')
        return 'Türkçe' if language == 'tr' else 'İngilizce'

    def extract_keywords(self, description: str, categories: List[str]) -> List[str]:
        """Anahtar kelimeler çıkar"""
        keywords = []
        
        # Kategorilerden
        for category in categories:
            keywords.extend(category.lower().split())
        
        # Açıklamadan
        if description:
            desc_words = description.lower().split()
            keywords.extend([w for w in desc_words if len(w) > 3])
        
        # Türkçe anahtar kelimeler
        keywords.extend(self.turkish_keywords)
        
        return list(set(keywords))[:10]  # Max 10 anahtar kelime

    def ingest_books(self, target_count: int = 1000):
        """Ana ingestion fonksiyonu"""
        print(f"Kitap verisi toplama başlıyor... Hedef: {target_count}")
        
        # Türlere göre arama
        for genre in self.genres:
            if len(self.books) >= target_count:
                break
                
            print(f"{genre} türünde kitap aranıyor...")
            
            # İngilizce arama
            query = f"subject:{genre}"
            books = self.search_books(query, 40)
            
            for book in books:
                if len(self.books) >= target_count:
                    break
                    
                parsed_book = self.parse_book(book)
                if parsed_book['baslik'] not in [b['baslik'] for b in self.books]:
                    self.books.append(parsed_book)
            
            # Türkçe arama
            for tr_keyword in self.turkish_keywords[:5]:  # İlk 5 Türkçe kelime
                if len(self.books) >= target_count:
                    break
                    
                query = f"{tr_keyword} {genre}"
                books = self.search_books(query, 20)
                
                for book in books:
                    if len(self.books) >= target_count:
                        break
                        
                    parsed_book = self.parse_book(book)
                    if parsed_book['baslik'] not in [b['baslik'] for b in self.books]:
                        self.books.append(parsed_book)
            
            # API limit aşımını önle
            time.sleep(1)
        
        print(f"Toplam {len(self.books)} kitap toplandı!")
        return self.books

    def save_to_json(self, filename: str = '../data/books.json'):
        """JSON dosyasına kaydet"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.books, f, ensure_ascii=False, indent=2)
        print(f"Kitaplar {filename} dosyasına kaydedildi!")

def main():
    ingester = BookIngester()
    books = ingester.ingest_books(1000)
    ingester.save_to_json()
    
    # İstatistikler
    genres = {}
    for book in books:
        genre = book['tur']
        genres[genre] = genres.get(genre, 0) + 1
    
    print("\nTür dağılımı:")
    for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True):
        print(f"{genre}: {count}")

if __name__ == "__main__":
    main()
