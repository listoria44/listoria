#!/usr/bin/env python3
"""
Tüm ingestion scriptlerini çalıştıran ana script
"""

import os
import sys
import subprocess
import time

def run_script(script_name, description):
    """Script çalıştır ve sonucu raporla"""
    print(f"\n{'='*50}")
    print(f"🚀 {description} başlıyor...")
    print(f"📁 Script: {script_name}")
    print(f"{'='*50}")
    
    try:
        # Script'i çalıştır
        result = subprocess.run([
            sys.executable, script_name
        ], capture_output=True, text=True, cwd='scripts')
        
        if result.returncode == 0:
            print(f"✅ {description} başarıyla tamamlandı!")
            print("📊 Çıktı:")
            print(result.stdout)
        else:
            print(f"❌ {description} hatası!")
            print("🔍 Hata detayı:")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Script çalıştırma hatası: {e}")
    
    print(f"{'='*50}\n")

def main():
    """Ana ingestion süreci"""
    print("🎯 Listoria - Otomatik Data Ingestion Sistemi")
    print("📊 Hedef: Kitap 1K, Film 500, Dizi 500, Müzik 2K")
    print("\n⚠️  ÖNEMLİ: API anahtarlarını .env dosyanıza ekleyin (örnek için .env.example).")

    required_envs = [
        ("GOOGLE_BOOKS_API_KEY", "Google Books API"),
        ("TMDB_API_KEY", "TMDB API"),
        ("LASTFM_API_KEY", "Last.fm API"),
        ("SPOTIFY_CLIENT_ID", "Spotify Client ID"),
        ("SPOTIFY_CLIENT_SECRET", "Spotify Client Secret"),
    ]
    missing = [key for key, _ in required_envs if not os.getenv(key)]
    if missing:
        print("⚠️ Eksik ortam değişkenleri:", ", ".join(missing))
        print("Lütfen .env dosyanızı doldurun ve tekrar deneyin.")
    
    # Script listesi
    scripts = [
        ("ingest_books.py", "Kitap Verisi Toplama (Google Books API)"),
        ("ingest_movies.py", "Film Verisi Toplama (TMDB API)"),
        ("ingest_series.py", "Dizi Verisi Toplama (TMDB API)"),
        ("ingest_music.py", "Müzik Verisi Toplama (Last.fm + Spotify API)")
    ]
    
    # Her script'i çalıştır
    for script_name, description in scripts:
        if os.path.exists(f"scripts/{script_name}"):
            run_script(script_name, description)
            time.sleep(2)  # Script'ler arası bekleme
        else:
            print(f"❌ Script bulunamadı: {script_name}")
    
    print("🎉 Tüm ingestion süreçleri tamamlandı!")
    print("\n📁 Data dosyaları 'data/' klasöründe oluşturuldu:")
    print("   📚 books.json - Kitap verileri")
    print("   🎬 movies.json - Film verileri")
    print("   📺 series.json - Dizi verileri")
    print("   🎵 music.json - Müzik verileri")
    
    print("\n🔧 Sonraki adımlar:")
    print("   1. app.py'deki get_all_*_database() fonksiyonlarını JSON okumaya güncelleyin")
    print("   2. Uygulamayı test edin")
    print("   3. Gerekirse daha fazla veri ekleyin")

if __name__ == "__main__":
    main()
