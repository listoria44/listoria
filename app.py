from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import timedelta
import sqlite3
import random
import smtplib
import ssl
from email.message import EmailMessage
import requests
import json
import os
from dotenv import load_dotenv
from oauthlib.oauth2 import WebApplicationClient
import hashlib
import base64
import urllib.parse
from config import Config
import time
import psycopg2

# Güvenli olmayan bağlantılar için OAuth2 kütüphanesine izin ver
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

load_dotenv()
config = Config()

app = Flask(__name__)
# Secret key ortam değişkeninden alınır
app.secret_key = config.SECRET_KEY
app.permanent_session_lifetime = timedelta(days=30)

# Google Login Ayarları
GOOGLE_CLIENT_ID = config.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = config.GOOGLE_CLIENT_SECRET
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# E-POSTA AYARLARI
SENDER_EMAIL = config.SENDER_EMAIL
SENDER_PASSWORD = config.SENDER_PASSWORD

# Spotify API Ayarları
SPOTIFY_CLIENT_ID = config.SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET = config.SPOTIFY_CLIENT_SECRET

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

def get_db_connection():
    # Eğer DATABASE_URL ortam değişkeni varsa (Render'daysa), PostgreSQL'e bağlan
    if 'DATABASE_URL' in os.environ:
        # URL'yi ortam değişkeninden çek ve PostgreSQL'e bağlan
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        conn.autocommit = True 
        return conn
    
    # Yoksa (yerel bilgisayardaysan), SQLite'a bağlanmaya devam et
    else:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn

def create_db_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            kullanici_adi TEXT,
            sifre TEXT NOT NULL,
            dogum_tarihi TEXT
        );
    ''')
    conn.close()

create_db_table()

verification_codes = {}
password_reset_codes = {}

def send_email(receiver_email, subject, body):
    # E-posta ayarları zorunlu kontrol
    if not config.has_email_config:
        app.logger.error("E-posta ayarları eksik. Lütfen .env dosyasında SENDER_EMAIL ve SENDER_PASSWORD ayarlayın.")
        return False
        
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = config.SENDER_EMAIL
        msg['To'] = receiver_email
        
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
            smtp.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
            smtp.send_message(msg)
        
        app.logger.info(f"E-posta başarıyla gönderildi: {receiver_email}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        app.logger.error(f"E-posta kimlik doğrulama hatası. Gmail App Password kontrol edin.")
        return False
    except smtplib.SMTPException as e:
        app.logger.error(f"SMTP hatası: {str(e)}")
        return False
    except Exception as e:
        app.logger.error(f"E-posta gönderme hatası: {str(e)}")
        return False

@app.route('/')
def home():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'logged_in' in session:
        # Kullanıcı bilgisini ve yaşını şablona ilet (profil için)
        kullanici_adi = session.get('kullanici_adi')
        conn = get_db_connection()
        row = conn.execute('SELECT kullanici_adi, dogum_tarihi, email FROM kullanicilar WHERE kullanici_adi = ?', (kullanici_adi,)).fetchone()
        conn.close()

        yas = None
        if row and row['dogum_tarihi'] and row['dogum_tarihi'] != 'N/A':
            try:
                dogum_yili = int(str(row['dogum_tarihi']).split('-')[0])
                yas = 2024 - dogum_yili
            except Exception:
                yas = None

        profil = {
            'kullanici_adi': row['kullanici_adi'] if row else kullanici_adi,
            'email': row['email'] if row else None,
            'yas': yas,
            'dogum_tarihi': row['dogum_tarihi'] if row else None,
        }
        
        # API durumları
        api_durumu = {
            'google_books': config.has_google_books_api,
            'tmdb': config.has_tmdb_api,
            'hugging_face': config.has_hugging_face_api,
            'lastfm': config.has_lastfm_api,
            'spotify': config.has_spotify_config,
            'email': config.has_email_config
        }

        return render_template('recommender.html', profil=profil, api_durumu=api_durumu)
    else:
        return redirect(url_for('home'))

@app.route('/giris', methods=['POST'])
def giris():
    email = request.form['email']
    sifre = request.form['sifre']
    beni_hatirla = request.form.get('beni_hatirla')
    
    if not email or not sifre:
        return render_template('index.html', hata="Lütfen tüm alanları doldurunuz.")
    
    conn = get_db_connection()
    kullanici = conn.execute('SELECT * FROM kullanicilar WHERE email = ? AND sifre = ?', (email, sifre)).fetchone()
    conn.close()

    if kullanici:
        session['logged_in'] = True
        session['kullanici_adi'] = kullanici['kullanici_adi']
        if beni_hatirla:
            session.permanent = True
        return redirect(url_for('dashboard'))
    else:
        return render_template('index.html', hata="Hatalı e-posta veya şifre!")

@app.route('/kayit')
def kayit():
    return render_template('register.html')

@app.route('/kayit-ol', methods=['POST'])
def kayit_ol():
    try:
        email = request.form.get('email')
        kullanici_adi = request.form.get('kullanici_adi')
        sifre = request.form.get('sifre')
        dogum_tarihi = request.form.get('dogum_tarihi')
        
        if not email or not sifre or not dogum_tarihi or not kullanici_adi:
            return render_template('register.html', hata="Lütfen tüm alanları doldurunuz.")
        
        # Yaş kontrolü - artık 13+ (gençler için)
        from datetime import datetime
        try:
            birth_date = datetime.strptime(dogum_tarihi, '%Y-%m-%d')
            today = datetime.now()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            
            if age < 13:
                return render_template('register.html', hata="Bu hizmet 13 yaş ve üzeri kullanıcılar içindir.")
        except ValueError:
            return render_template('register.html', hata="Geçerli bir doğum tarihi giriniz.")
            
        conn = get_db_connection()
        user_exists = conn.execute('SELECT 1 FROM kullanicilar WHERE email = ?', (email,)).fetchone()
        
        if user_exists:
            conn.close()
            return render_template('register.html', hata="Bu e-posta adresi zaten kayıtlı!")
        
        # Gerçek e-posta doğrulama sistemi
        verification_code = str(random.randint(100000, 999999))
        verification_codes[email] = {
            'code': verification_code,
            'kullanici_adi': kullanici_adi,
            'sifre': sifre,
            'dogum_tarihi': dogum_tarihi
        }
        
        subject = "Listoria - Hesap Doğrulama Kodu"
        body = f"""Merhaba {kullanici_adi},

Listoria'ya hoş geldin! Hesabını doğrulamak için aşağıdaki 6 haneli kodu kullan:

🔐 Doğrulama Kodu: {verification_code}

Bu kod 15 dakika boyunca geçerlidir. Güvenliğin için bu kodu kimseyle paylaşma.

Eğer bu hesabı sen oluşturmadıysan, bu e-postayı görmezden gel.

Listoria Ekibi
📚🎬🎵 Senin için en iyi önerileri buluyoruz!"""
        
        email_sent = send_email(email, subject, body)
        
        if email_sent:
            app.logger.info(f"Doğrulama kodu gönderildi: {email}")
            return redirect(url_for('dogrulama', email=email))
        else:
            app.logger.error(f"E-posta gönderilemedi: {email}")
            return render_template('register.html', hata="E-posta gönderimi başarısız. Lütfen e-posta adresinizi kontrol edin veya daha sonra tekrar deneyin.")
    except Exception as e:
        app.logger.error(f"Kayıt olma hatası: {str(e)}")
        return render_template('register.html', hata="Kayıt olma işlemi sırasında bir hata oluştu. Lütfen tekrar deneyin.")

@app.route('/cikis')
def cikis():
    session.pop('logged_in', None)
    session.pop('kullanici_adi', None)
    return redirect(url_for('home'))

@app.route('/dogrulama')
def dogrulama():
    email = request.args.get('email')
    if not email or email not in verification_codes:
        return redirect(url_for('kayit'))
    return render_template('verification.html', email=email)

@app.route('/dogrula', methods=['POST'])
def dogrula():
    email = request.form['email']
    girilen_kod = request.form['kod']

    if not girilen_kod or not email:
        return render_template('verification.html', email=email, hata="Lütfen kodu giriniz.")
    
    if email not in verification_codes:
        return render_template('register.html', hata="Geçersiz doğrulama isteği. Lütfen tekrar kayıt olunuz.")

    if verification_codes[email]['code'] == girilen_kod:
        sifre = verification_codes[email]['sifre']
        kullanici_adi = verification_codes[email]['kullanici_adi']
        dogum_tarihi = verification_codes[email]['dogum_tarihi']
        
        conn = get_db_connection()
        conn.execute('INSERT INTO kullanicilar (email, kullanici_adi, sifre, dogum_tarihi) VALUES (?, ?, ?, ?)', (email, kullanici_adi, sifre, dogum_tarihi))
        conn.commit()
        conn.close()
        
        del verification_codes[email]
        
        session['logged_in'] = True
        session['kullanici_adi'] = kullanici_adi
        return redirect(url_for('dashboard'))
    else:
        verification_codes.pop(email, None)  # Güvenli silme
        return render_template('verification.html', email=email, hata="Hatalı doğrulama kodu! Lütfen tekrar kayıt olunuz.")

# ============= ÖNERİ SİSTEMİ ROUTE'LARI =============

@app.route('/oneri/<kategori>')
def oneri_sayfasi(kategori):
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = conn.execute('SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?', 
                           (session['kullanici_adi'],)).fetchone()
    conn.close()
    
    # Yaş hesaplama (basit bir yaklaşım)
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            from datetime import datetime
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
            yas = datetime.now().year - dogum_yili
        except:
            yas = None
    
    if kategori == 'kitap':
        # Önceki arama kriterlerini al (varsa)
        son_arama = session.get('son_arama', {})
        return render_template('kitap_oneri.html', yas=yas, son_arama=son_arama)
    elif kategori == 'dizi':
        return render_template('dizi_oneri.html', yas=yas)
    elif kategori == 'film':
        return render_template('film_oneri.html', yas=yas)
    elif kategori == 'muzik':
        return render_template('muzik_oneri.html', yas=yas)
    else:
        return redirect(url_for('dashboard'))

@app.route('/kitap-oneri-al', methods=['POST'])
def kitap_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    # Form verilerini al
    kitap1 = request.form.get('kitap1')
    kitap2 = request.form.get('kitap2') 
    kitap3 = request.form.get('kitap3')
    kitap4 = request.form.get('kitap4')
    kitap5 = request.form.get('kitap5')
    min_sayfa = request.form.get('min_sayfa')
    max_sayfa = request.form.get('max_sayfa')
    tur = request.form.get('tur')
    notlar = request.form.get('notlar')
    
    # Boş olmayan kitapları listele
    kullanici_kitaplari = [k for k in [kitap1, kitap2, kitap3, kitap4, kitap5] if k and k.strip()]
    
    # En az 3 kitap kontrolü
    if len(kullanici_kitaplari) < 3:
        return render_template('kitap_oneri.html', hata="En az 3 roman girmelisiniz.", yas=None, son_arama={})
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = conn.execute('SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?', 
                           (session['kullanici_adi'],)).fetchone()
    conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            from datetime import datetime
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
            yas = datetime.now().year - dogum_yili
        except:
            yas = None
    
    # Gelişmiş AI öneri algoritması
    try:
        oneriler = generate_book_recommendations(kullanici_kitaplari, yas, tur, min_sayfa, max_sayfa, notlar)
    except Exception as e:
        app.logger.error(f"Kitap öneri hatası: {str(e)}")
        return render_template('kitap_oneri.html', hata="Öneri oluşturulurken bir hata oluştu.", yas=yas, son_arama={})
    
    # Arama kriterlerini session'da sakla
    session['son_arama'] = {
        'kitap1': kitap1 or '',
        'kitap2': kitap2 or '', 
        'kitap3': kitap3 or '',
        'kitap4': kitap4 or '',
        'kitap5': kitap5 or '',
        'min_sayfa': min_sayfa or '',
        'max_sayfa': max_sayfa or '',
        'tur': tur or '',
        'notlar': notlar or ''
    }
    
    return render_template('kitap_sonuc.html', 
                         oneriler=oneriler,
                         kullanici_kitaplari=kullanici_kitaplari,
                         yas=yas)

@app.route('/film-oneri-al', methods=['POST'])
def film_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    film1 = request.form.get('film1')
    film2 = request.form.get('film2')
    film3 = request.form.get('film3')
    film4 = request.form.get('film4')
    film5 = request.form.get('film5')
    tur = request.form.get('tur')
    notlar = request.form.get('notlar', '')
    
    kullanici_filmleri = [film for film in [film1, film2, film3, film4, film5] if film and film.strip()]
    
    if len(kullanici_filmleri) < 3:
        return render_template('film_oneri.html', hata="En az 3 film girmelisiniz.", yas=None)
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = conn.execute('SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?', 
                           (session['kullanici_adi'],)).fetchone()
    conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
            yas = 2024 - dogum_yili
        except:
            yas = None
    
    try:
        oneriler = generate_film_recommendations(kullanici_filmleri, yas, tur, notlar)
    except Exception as e:
        app.logger.error(f"Film öneri hatası: {str(e)}")
        return render_template('film_oneri.html', hata="Öneri oluşturulurken bir hata oluştu.", yas=yas)
    
    return render_template('film_sonuc.html', oneriler=oneriler, kullanici_filmleri=kullanici_filmleri, yas=yas)

@app.route('/dizi-oneri-al', methods=['POST'])
def dizi_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    dizi1 = request.form.get('dizi1')
    dizi2 = request.form.get('dizi2')
    dizi3 = request.form.get('dizi3')
    dizi4 = request.form.get('dizi4')
    dizi5 = request.form.get('dizi5')
    tur = request.form.get('tur')
    notlar = request.form.get('notlar', '')
    
    kullanici_dizileri = [dizi for dizi in [dizi1, dizi2, dizi3, dizi4, dizi5] if dizi and dizi.strip()]
    
    if len(kullanici_dizileri) < 3:
        return render_template('dizi_oneri.html', hata="En az 3 dizi girmelisiniz.", yas=None)
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = conn.execute('SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?', 
                           (session['kullanici_adi'],)).fetchone()
    conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
            yas = 2024 - dogum_yili
        except:
            yas = None
    
    try:
        oneriler = generate_series_recommendations(kullanici_dizileri, yas, tur, notlar)
    except Exception as e:
        app.logger.error(f"Dizi öneri hatası: {str(e)}")
        return render_template('dizi_oneri.html', hata="Öneri oluşturulurken bir hata oluştu.", yas=yas)
    
    return render_template('dizi_sonuc.html', oneriler=oneriler, kullanici_dizileri=kullanici_dizileri, yas=yas)

@app.route('/muzik-oneri-al', methods=['POST'])
def muzik_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    muzik1 = request.form.get('muzik1')
    muzik2 = request.form.get('muzik2')
    muzik3 = request.form.get('muzik3')
    muzik4 = request.form.get('muzik4')
    muzik5 = request.form.get('muzik5')
    tur = request.form.get('tur')
    notlar = request.form.get('notlar', '')
    oneri_turu = request.form.get('oneri_turu', 'standard')  # Yeni eklenen
    
    kullanici_muzikleri = [muzik for muzik in [muzik1, muzik2, muzik3, muzik4, muzik5] if muzik and muzik.strip()]
    
    if len(kullanici_muzikleri) < 3:
        return render_template('muzik_oneri.html', hata="En az 3 şarkı girmelisiniz.", yas=None)
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = conn.execute('SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?', 
                           (session['kullanici_adi'],)).fetchone()
    conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
            yas = 2024 - dogum_yili
        except:
            yas = None
    
    try:
        oneriler = generate_music_recommendations(kullanici_muzikleri, yas, tur, notlar)
        
        # Spotify playlist oluştur (eğer playlist modu seçildiyse)
        playlist_data = None
        if oneri_turu == 'spotify_playlist':
            playlist_data = create_spotify_playlist(
                kullanici_muzikleri + [f"{o['baslik']} - {o['sanatci']}" for o in oneriler[:10]], 
                tur
            )
        
        return render_template('muzik_sonuc.html', 
                             oneriler=oneriler, 
                             kullanici_muzikleri=kullanici_muzikleri, 
                             yas=yas,
                             spotify_playlist=playlist_data,
                             oneri_turu=oneri_turu)
    except Exception as e:
        app.logger.error(f"Müzik öneri hatası: {str(e)}")
        return render_template('muzik_oneri.html', hata=f"Öneri oluşturulurken bir hata oluştu: {str(e)}", yas=yas)

# ============= API ENTEGRASYONLARı =============

def fetch_google_books_api(query, max_results=10):
    """Google Books API'den kitap verisi çeker"""
    if not config.has_google_books_api:
        app.logger.warning("Google Books API anahtarı yok, manuel veri kullanılıyor")
        return []
    
    try:
        url = f"https://www.googleapis.com/books/v1/volumes"
        params = {
            'q': query,
            'maxResults': max_results,
            'key': config.GOOGLE_BOOKS_API_KEY,
            'printType': 'books',
            'orderBy': 'relevance'
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            books = []
            
            for item in data.get('items', []):
                volume_info = item.get('volumeInfo', {})
                book = {
                    'baslik': volume_info.get('title', 'Bilinmeyen'),
                    'yazar': ', '.join(volume_info.get('authors', ['Bilinmeyen Yazar'])),
                    'sayfa': volume_info.get('pageCount', 0),
                    'tur': ', '.join(volume_info.get('categories', ['Genel'])),
                    'aciklama': volume_info.get('description', '')[:200] + '...' if volume_info.get('description') else '',
                    'yas_uygun': True,  # API'den yaş kısıtlaması gelmiyor, varsağılan True
                    'tema': volume_info.get('categories', []),
                    'yazar_tarzi': 'api_data',
                    'neden': f"Google Books'tan önerilen: {volume_info.get('title', '')}",
                    'puan': 0,
                    'api_source': 'google_books'
                }
                books.append(book)
            
            app.logger.info(f"Google Books API'den {len(books)} kitap getirildi")
            return books
        else:
            app.logger.error(f"Google Books API hatası: {response.status_code}")
            return []
            
    except Exception as e:
        app.logger.error(f"Google Books API isteği başarısız: {str(e)}")
        return []

def fetch_tmdb_movies_api(query, max_results=10):
    """TMDB API'den film verisi çeker"""
    if not config.has_tmdb_api:
        app.logger.warning("TMDB API anahtarı yok, manuel veri kullanılıyor")
        return []
    
    try:
        url = f"https://api.themoviedb.org/3/search/movie"
        params = {
            'api_key': config.TMDB_API_KEY,
            'query': query,
            'language': 'tr-TR',  # Türkçe sonuçlar için
            'page': 1
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            movies = []
            
            for item in data.get('results', [])[:max_results]:
                movie = {
                    'baslik': item.get('title', 'Bilinmeyen'),
                    'yonetmen': 'TMDB Verisi',  # Detaylı veri için ayrı istek gerekli
                    'dakika': 0,  # Detaylı veri için ayrı istek gerekli
                    'tur': 'TMDB',
                    'yas_uygun': not item.get('adult', False),
                    'tema': [item.get('original_language', 'en')],
                    'yonetmen_tarzi': 'api_data', 
                    'neden': f"TMDB'den önerilen: {item.get('overview', '')[:100]}...",
                    'puan': item.get('vote_average', 0),
                    'poster': f"https://image.tmdb.org/t/p/w300{item.get('poster_path', '')}" if item.get('poster_path') else '',
                    'api_source': 'tmdb'
                }
                movies.append(movie)
            
            app.logger.info(f"TMDB API'den {len(movies)} film getirildi")
            return movies
        else:
            app.logger.error(f"TMDB API hatası: {response.status_code}")
            return []
            
    except Exception as e:
        app.logger.error(f"TMDB API isteği başarısız: {str(e)}")
        return []

def fetch_tmdb_tv_api(query, max_results=10):
    """TMDB API'den dizi verisi çeker"""
    if not config.has_tmdb_api:
        app.logger.warning("TMDB API anahtarı yok, manuel veri kullanılıyor")
        return []
    
    try:
        url = f"https://api.themoviedb.org/3/search/tv"
        params = {
            'api_key': config.TMDB_API_KEY,
            'query': query,
            'language': 'tr-TR',
            'page': 1
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            series = []
            
            for item in data.get('results', [])[:max_results]:
                serie = {
                    'baslik': item.get('name', 'Bilinmeyen'),
                    'yaratici': 'TMDB Verisi',
                    'sezon': 0,  # Detaylı veri için ayrı istek gerekli
                    'tur': 'TMDB',
                    'yas_uygun': True,
                    'tema': [item.get('original_language', 'en')],
                    'yapimci_tarzi': 'api_data',
                    'neden': f"TMDB'den önerilen: {item.get('overview', '')[:100]}...",
                    'puan': item.get('vote_average', 0),
                    'poster': f"https://image.tmdb.org/t/p/w300{item.get('poster_path', '')}" if item.get('poster_path') else '',
                    'api_source': 'tmdb'
                }
                series.append(serie)
            
            app.logger.info(f"TMDB API'den {len(series)} dizi getirildi")
            return series
        else:
            app.logger.error(f"TMDB API hatası: {response.status_code}")
            return []
            
    except Exception as e:
        app.logger.error(f"TMDB API isteği başarısız: {str(e)}")
        return []

def fetch_lastfm_music_api(query, max_results=10):
    """Last.fm API'den müzik verisi çeker"""
    if not config.has_lastfm_api:
        app.logger.warning("Last.fm API anahtarı yok, manuel veri kullanılıyor")
        return []
    
    try:
        url = f"http://ws.audioscrobbler.com/2.0/"
        params = {
            'method': 'track.search',
            'track': query,
            'api_key': config.LASTFM_API_KEY,
            'format': 'json',
            'limit': max_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            tracks = []
            
            for item in data.get('results', {}).get('trackmatches', {}).get('track', []):
                track = {
                    'baslik': item.get('name', 'Bilinmeyen'),
                    'sanatci': item.get('artist', 'Bilinmeyen Sanatçı'),
                    'tur': 'Last.fm',  # Last.fm'den tür bilgisi almak için ekstra istek gerekli
                    'dil': 'Bilinmeyen',
                    'yil': 0,  # Last.fm'den yıl bilgisi almak için ekstra istek gerekli
                    'tema': ['api_data'],
                    'sanatci_tarzi': 'lastfm_data',
                    'yas_uygun': True,
                    'neden': f"Last.fm'den önerilen: {item.get('name', '')} - {item.get('artist', '')}",
                    'puan': int(item.get('listeners', 0)) / 1000,  # Dinleyici sayısına göre puan
                    'api_source': 'lastfm'
                }
                tracks.append(track)
            
            app.logger.info(f"Last.fm API'den {len(tracks)} şarkı getirildi")
            return tracks
        else:
            app.logger.error(f"Last.fm API hatası: {response.status_code}")
            return []
            
    except Exception as e:
        app.logger.error(f"Last.fm API isteği başarısız: {str(e)}")
        return []

def get_huggingface_ai_recommendation(user_input, content_type="book"):
    """Hugging Face AI'dan öneriler alır"""
    if not config.has_hugging_face_api:
        app.logger.warning("Hugging Face API anahtarı yok, yerel AI kullanılıyor")
        return []
    
    try:
        url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        headers = {"Authorization": f"Bearer {config.HUGGING_FACE_TOKEN}"}
        
        # Kullanıcı girdisini AI için optimize et
        if content_type == "book":
            prompt = f"Recommend books similar to: {user_input}. Give me 5 book titles with authors."
        elif content_type == "movie":
            prompt = f"Recommend movies similar to: {user_input}. Give me 5 movie titles with directors."
        elif content_type == "music":
            prompt = f"Recommend songs similar to: {user_input}. Give me 5 songs with artists."
        else:
            prompt = f"Recommend {content_type} similar to: {user_input}"
        
        payload = {"inputs": prompt}
        
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            ai_response = response.json()
            app.logger.info(f"Hugging Face AI'dan cevap alındı: {content_type}")
            return ai_response
        else:
            app.logger.error(f"Hugging Face API hatası: {response.status_code}")
            return []
            
    except Exception as e:
        app.logger.error(f"Hugging Face API isteği başarısız: {str(e)}")
        return []

# ============= İYİLEŞTİRİLMİŞ ÖNERİ ALGORİTMALARI (API ENTEGRELİ) =============

def generate_book_recommendations(kullanici_kitaplari, yas, tur, min_sayfa, max_sayfa, notlar):
    """API entegreli kitap öneri algoritması"""
    all_recommendations = []
    
    # 1. API'den veri çekmeyi dene
    if config.has_google_books_api:
        try:
            # Kullanıcı kitaplarından anahtar kelimeler çıkar
            search_terms = []
            for kitap in kullanici_kitaplari:
                search_terms.extend(kitap.split()[:2])  # İlk 2 kelimeyi al
            
            # Tür bilgisini ekle
            if tur and tur != 'hepsi':
                search_terms.append(tur)
            
            # Notlardan anahtar kelimeleri ekle
            if notlar:
                search_terms.extend(notlar.split()[:3])
            
            # API'den öneriler çek
            api_books_all = []
            for term in search_terms[:3]:  # İlk 3 terimle arama yap
                new_books = fetch_google_books_api(term, 5)
                
                # Duplicate kontrolü ile ekle
                for new_book in new_books:
                    new_title_lower = new_book['baslik'].lower().strip()
                    is_duplicate = False
                    
                    # Mevcut API kitaplarıyla karşılaştır
                    for existing_book in api_books_all:
                        existing_title_lower = existing_book['baslik'].lower().strip()
                        if (calculate_similarity(new_title_lower, existing_title_lower) > 0.8 or
                            new_title_lower == existing_title_lower):
                            is_duplicate = True
                            break
                    
                    # Kullanıcı kitaplarıyla karşılaştır
                    for user_book in kullanici_kitaplari:
                        user_book_lower = user_book.lower().strip()
                        if (calculate_similarity(new_title_lower, user_book_lower) > 0.8 or
                            user_book_lower in new_title_lower):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        api_books_all.append(new_book)
                
                time.sleep(0.5)  # API rate limit için
            
            all_recommendations.extend(api_books_all)
            
            app.logger.info(f"API'den {len(all_recommendations)} kitap önerisi alındı")
            
        except Exception as e:
            app.logger.error(f"API kitap önerisi hatası: {str(e)}")
    
    # Manuel veritabanından da öneri al (çeşitlilik için)
    manual_books = get_all_books_database()
    
    # Yaş filtreleme (13+ için gençler)
    if yas and yas < 13:
        manual_books = [k for k in manual_books if k.get('yas_uygun', True)]
    
    # Girilen kitapları çıkar (daha akıllı eşleştirme)
    girilen_kitaplar_lower = [kitap.lower().strip() for kitap in kullanici_kitaplari]
    filtered_manual = []
    
    for book in manual_books:
        is_duplicate = False
        book_title_lower = book['baslik'].lower().strip()
        book_author_lower = book.get('yazar', '').lower().strip()
        
        # API sonuçlarıyla çakışma kontrolü
        for api_book in all_recommendations:
            api_title_lower = api_book['baslik'].lower().strip()
            if (calculate_similarity(book_title_lower, api_title_lower) > 0.8 or 
                book_title_lower == api_title_lower):
                is_duplicate = True
                break
        
        # Kullanıcı kitaplarıyla çakışma kontrolü
        for girilen in girilen_kitaplar_lower:
            if (calculate_similarity(girilen, book_title_lower) > 0.8 or
                girilen in book_title_lower or book_title_lower in girilen or
                (book_author_lower and girilen in book_author_lower)):
                is_duplicate = True
                break
        
        # Zaten listedeki kitaplarla çakışma kontrolü
        for existing_book in filtered_manual:
            existing_title_lower = existing_book['baslik'].lower().strip()
            if (calculate_similarity(book_title_lower, existing_title_lower) > 0.8 or
                book_title_lower == existing_title_lower):
                is_duplicate = True
                break
        
        if not is_duplicate:
            filtered_manual.append(book)
    
    # Tür filtreleme (manuel veriler için)
    if tur and tur != 'hepsi':
        filtered_manual = [b for b in filtered_manual if b.get('tur', '').lower() == tur.lower()]
    
    # Sayfa filtreleme (manuel veriler için)
    if min_sayfa or max_sayfa:
        page_filtered = []
        for book in filtered_manual:
            pages = book.get('sayfa', 0)
            if min_sayfa and pages < int(min_sayfa):
                continue
            if max_sayfa and pages > int(max_sayfa):
                continue
            page_filtered.append(book)
        filtered_manual = page_filtered
    
    # Manuel önerileri ekle
    all_recommendations.extend(filtered_manual[:10])  # En fazla 10 manuel öneri
    
    # 3. Akıllı puanlama ve sıralama
    scored_recommendations = calculate_smart_book_similarity(all_recommendations, kullanici_kitaplari, notlar, yas)
    
    # 4. Çeşitlilik sağla: API ve manuel karışımı (duplicate kontrolle)
    final_recommendations = []
    used_titles = set()  # Başlıkları takip et
    api_count = 0
    manual_count = 0
    
    for book in scored_recommendations:
        if len(final_recommendations) >= 8:
            break
            
        book_title_lower = book['baslik'].lower().strip()
        
        # Başlık tekrarını kontrol et
        if book_title_lower in used_titles:
            continue
            
        # Kullanıcı kitaplarıyla son bir kez kontrol et
        is_user_book = False
        for user_book in kullanici_kitaplari:
            user_book_lower = user_book.lower().strip()
            if (calculate_similarity(book_title_lower, user_book_lower) > 0.8 or
                user_book_lower in book_title_lower or book_title_lower in user_book_lower):
                is_user_book = True
                break
        
        if is_user_book:
            continue
            
        if book.get('api_source') == 'google_books' and api_count < 7:
            final_recommendations.append(book)
            used_titles.add(book_title_lower)
            api_count += 1
        elif book.get('api_source') != 'google_books' and manual_count < 1:
            final_recommendations.append(book)
            used_titles.add(book_title_lower)
            manual_count += 1
    
    # Eğer yeterli öneri yoksa, kalan yerleri doldur
    if len(final_recommendations) < 8:
        remaining = 8 - len(final_recommendations)
        for book in scored_recommendations:
            if book not in final_recommendations and remaining > 0:
                final_recommendations.append(book)
                remaining -= 1
    
    app.logger.info(f"Toplam {len(final_recommendations)} kitap önerisi hazırlandı (API: {api_count}, Manuel: {manual_count})")
    return final_recommendations[:8]

def generate_film_recommendations(kullanici_filmleri, yas, tur, notlar):
    """API entegreli film öneri algoritması"""
    all_recommendations = []
    
    # 1. TMDB API'den veri çekmeyi dene
    if config.has_tmdb_api:
        try:
            # Kullanıcı filmlerinden anahtar kelimeler çıkar
            search_terms = []
            for film in kullanici_filmleri:
                search_terms.extend(film.split()[:2])
            
            # Tür ve notları ekle
            if tur and tur != 'hepsi':
                search_terms.append(tur)
            if notlar:
                search_terms.extend(notlar.split()[:3])
            
            # API'den öneriler çek
            for term in search_terms[:3]:
                api_movies = fetch_tmdb_movies_api(term, 5)
                all_recommendations.extend(api_movies)
                time.sleep(0.5)
            
            app.logger.info(f"TMDB API'den {len(all_recommendations)} film önerisi alındı")
            
        except Exception as e:
            app.logger.error(f"API film önerisi hatası: {str(e)}")
    
    # 2. Manuel veritabanından öneri al
    manual_movies = get_all_films_database()
    
    # Yaş filtreleme (13+ gençler için)
    if yas and yas < 13:
        manual_movies = [film for film in manual_movies if film.get('yas_uygun', True)]
    
    # Kullanıcı filmlerini çıkar
    kullanici_filmleri_lower = [film.lower().strip() for film in kullanici_filmleri]
    filtered_manual = []
    
    for movie in manual_movies:
        is_duplicate = False
        movie_title_lower = movie['baslik'].lower().strip()
        
        # API sonuçlarıyla çakışma kontrolü
        for api_movie in all_recommendations:
            api_title_lower = api_movie['baslik'].lower().strip()
            if (calculate_similarity(movie_title_lower, api_title_lower) > 0.8 or 
                movie_title_lower == api_title_lower):
                is_duplicate = True
                break
        
        # Kullanıcı filmleriyle çakışma kontrolü
        for user_film in kullanici_filmleri_lower:
            if (calculate_similarity(movie_title_lower, user_film) > 0.8 or
                user_film in movie_title_lower or movie_title_lower in user_film):
                is_duplicate = True
                break
        
        # Önceki önerilerle çakışma kontrolü
        for existing_movie in filtered_manual:
            existing_title_lower = existing_movie['baslik'].lower().strip()
            if (calculate_similarity(movie_title_lower, existing_title_lower) > 0.8 or
                movie_title_lower == existing_title_lower):
                is_duplicate = True
                break
        
        if not is_duplicate:
            filtered_manual.append(movie)
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_manual = [film for film in filtered_manual if film.get('tur', '') == tur]
    
    # Manuel önerileri ekle (7:1 oranı için az sayıda)
    all_recommendations.extend(filtered_manual[:2])  # En fazla 2 manuel film
    
    # AI skorlama
    scored_oneriler = calculate_film_similarity_scores(all_recommendations, kullanici_filmleri, notlar)
    
    return scored_oneriler[:8]

def generate_series_recommendations(kullanici_dizileri, yas, tur, notlar):
    """API entegreli dizi öneri algoritması"""
    all_recommendations = []
    
    # 1. TMDB API'den dizi verisi çek
    if config.has_tmdb_api:
        try:
            search_terms = []
            for dizi in kullanici_dizileri:
                search_terms.extend(dizi.split()[:2])
            
            if tur and tur != 'hepsi':
                search_terms.append(tur)
            if notlar:
                search_terms.extend(notlar.split()[:3])
            
            for term in search_terms[:3]:
                api_series = fetch_tmdb_tv_api(term, 5)
                all_recommendations.extend(api_series)
                time.sleep(0.5)
            
            app.logger.info(f"TMDB API'den {len(all_recommendations)} dizi önerisi alındı")
            
        except Exception as e:
            app.logger.error(f"API dizi önerisi hatası: {str(e)}")
    
    # 2. Manuel veritabanı
    manual_series = get_all_series_database()
    
    # Yaş filtreleme (13+ gençler için)
    if yas and yas < 13:
        manual_series = [dizi for dizi in manual_series if dizi.get('yas_uygun', True)]
    
    # Kullanıcı dizilerini çıkar
    kullanici_dizileri_lower = [dizi.lower() for dizi in kullanici_dizileri]
    filtered_manual = []
    
    for serie in manual_series:
        is_duplicate = False
        serie_title_lower = serie['baslik'].lower()
        
        # API sonuçlarıyla çakışma kontrolü
        for api_serie in all_recommendations:
            if calculate_similarity(serie_title_lower, api_serie['baslik'].lower()) > 0.7:
                is_duplicate = True
                break
        
        if serie_title_lower not in kullanici_dizileri_lower and not is_duplicate:
            filtered_manual.append(serie)
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_manual = [dizi for dizi in filtered_manual if dizi.get('tur', '') == tur]
    
    # Manuel önerileri ekle (7:1 oranı için az sayıda)
    all_recommendations.extend(filtered_manual[:2])  # En fazla 2 manuel dizi
    
    # AI skorlama
    scored_oneriler = calculate_series_similarity_scores(all_recommendations, kullanici_dizileri, notlar)
    
    return scored_oneriler[:8]

def generate_music_recommendations(kullanici_muzikleri, yas, tur, notlar):
    """API entegreli müzik öneri algoritması"""
    all_recommendations = []
    
    # 1. Last.fm API'den müzik verisi çek
    if config.has_lastfm_api:
        try:
            search_terms = []
            for muzik in kullanici_muzikleri:
                # Şarkı adından sanatçı ayırma dene
                if ' - ' in muzik:
                    track, artist = muzik.split(' - ', 1)
                    search_terms.append(track.strip())
                    search_terms.append(artist.strip())
                else:
                    search_terms.extend(muzik.split()[:2])
            
            if tur and tur != 'hepsi':
                search_terms.append(tur)
            if notlar:
                search_terms.extend(notlar.split()[:3])
            
            for term in search_terms[:3]:
                api_music = fetch_lastfm_music_api(term, 5)
                all_recommendations.extend(api_music)
                time.sleep(0.5)
            
            app.logger.info(f"Last.fm API'den {len(all_recommendations)} şarkı önerisi alındı")
            
        except Exception as e:
            app.logger.error(f"API müzik önerisi hatası: {str(e)}")
    
    # 2. Manuel veritabanından öneri al
    manual_music = get_all_music_database()
    
    # Yaş filtreleme (13+ gençler için)
    if yas and yas < 13:
        manual_music = [muzik for muzik in manual_music if muzik.get('yas_uygun', True)]
    
    # Kullanıcı müziklerini çıkar
    kullanici_muzikleri_lower = [muzik.lower().strip() for muzik in kullanici_muzikleri]
    filtered_manual = []
    
    for music in manual_music:
        is_duplicate = False
        music_title_lower = music['baslik'].lower().strip()
        music_artist_lower = music.get('sanatci', '').lower().strip()
        
        # API sonuçlarıyla çakışma kontrolü
        for api_music in all_recommendations:
            api_title_lower = api_music['baslik'].lower().strip()
            api_artist_lower = api_music.get('sanatci', '').lower().strip()
            
            if (calculate_similarity(music_title_lower, api_title_lower) > 0.8 or 
                music_title_lower == api_title_lower or
                (music_artist_lower and api_artist_lower and 
                 calculate_similarity(music_artist_lower, api_artist_lower) > 0.8)):
                is_duplicate = True
                break
        
        # Kullanıcı müzikleriyle çakışma kontrolü
        for user_music in kullanici_muzikleri_lower:
            if (calculate_similarity(music_title_lower, user_music) > 0.8 or
                user_music in music_title_lower or music_title_lower in user_music or
                (music_artist_lower and user_music in music_artist_lower)):
                is_duplicate = True
                break
        
        # Önceki önerilerle çakışma kontrolü
        for existing_music in filtered_manual:
            existing_title_lower = existing_music['baslik'].lower().strip()
            existing_artist_lower = existing_music.get('sanatci', '').lower().strip()
            
            if (calculate_similarity(music_title_lower, existing_title_lower) > 0.8 or
                music_title_lower == existing_title_lower or
                (music_artist_lower and existing_artist_lower and
                 music_artist_lower == existing_artist_lower)):
                is_duplicate = True
                break
        
        if not is_duplicate:
            filtered_manual.append(music)
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_manual = [muzik for muzik in filtered_manual if muzik.get('tur', '') == tur]
    
    # Eğer filtrelenmiş öneri yoksa, tüm müzikleri kullan
    if not filtered_manual and not all_recommendations:
        filtered_manual = manual_music[:4]  # Acil durum için 4 adet
    
    # Manuel önerileri ekle (7:1 oranı için az sayıda)
    all_recommendations.extend(filtered_manual[:2])  # En fazla 2 manuel müzik
    
    # AI skorlama
    scored_oneriler = calculate_music_similarity_scores(all_recommendations, kullanici_muzikleri, notlar)
    
    return scored_oneriler[:8]

# ============= SPOTIFY PLAYLIST =============

def create_spotify_playlist(sarkilar, tur=None):
    """Spotify playlist oluştur (simüle edilmiş)"""
    try:
        # Playlist için unique ID oluştur
        playlist_content = ''.join(sarkilar)
        playlist_hash = hashlib.md5(playlist_content.encode()).hexdigest()[:8]
        playlist_id = f"listoria_{playlist_hash}"
        
        # Playlist bilgileri
        playlist_data = {
            'id': playlist_id,
            'name': f"Listoria - {tur.title() if tur and tur != 'hepsi' else 'Karışık'} Playlist",
            'url': f"https://open.spotify.com/playlist/{playlist_id}",
            'tracks': sarkilar[:20],  # İlk 20 şarkı
            'description': 'Listoria AI tarafından oluşturulan playlist',
            'demo': True  # API olmadığı için demo mod
        }
        
        return playlist_data
        
    except Exception as e:
        app.logger.error(f"Spotify playlist oluşturma hatası: {str(e)}")
        return {
            'id': 'demo_playlist',
            'name': 'Listoria Demo Playlist',
            'url': 'https://open.spotify.com/playlist/demo',
            'tracks': sarkilar[:10],
            'demo': True
        }

# ============= PUANLAMA ALGORİTMALARI =============

def calculate_similarity(str1, str2):
    """İki string arasındaki benzerlik oranını hesaplar (0-1 arası)"""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

def calculate_smart_book_similarity(kitaplar, kullanici_kitaplari, notlar, yas):
    """Akıllı kitap benzerlik puanlaması - API olmadan"""
    import random
    from datetime import datetime
    
    for kitap in kitaplar:
        puan = 0
        
        # Gerekli anahtarların varlığını kontrol et
        if not all(key in kitap for key in ['baslik', 'tur']):
            kitap['puan'] = 0
            continue
            
        # 1. Notlar analizi (en önemli - %50)
        notlar_puani = 0
        if notlar and notlar.strip():
            notlar_lower = notlar.lower()
            notlar_kelimeleri = notlar_lower.split()
            
            # Tema eşleşmesi
            for tema in kitap.get('tema', []):
                if tema.lower() in notlar_lower:
                    notlar_puani += 15
            
            # Tür eşleşmesi
            if kitap.get('tur', '').lower() in notlar_lower:
                notlar_puani += 20
            
            # Yazar tarzı eşleşmesi
            if kitap.get('yazar_tarzi', '').lower() in notlar_lower:
                notlar_puani += 10
            
            # Kitap başlığı kelime eşleşmesi
            kitap_kelimeleri = kitap['baslik'].lower().split()
            for kelime in notlar_kelimeleri:
                if kelime in kitap_kelimeleri:
                    notlar_puani += 5
        
        # 2. Kullanıcı tercihleri analizi (%30)
        tercih_puani = 0
        for kullanici_kitap in kullanici_kitaplari:
            kullanici_lower = kullanici_kitap.lower()
            
            # Yazar eşleşmesi
            if kitap.get('yazar', '').lower() in kullanici_lower:
                tercih_puani += 25
            
            # Tema eşleşmesi
            for tema in kitap.get('tema', []):
                if tema in kullanici_lower:
                    tercih_puani += 8
            
            # Tür eşleşmesi
            if kitap.get('tur', '').lower() == kullanici_kitap.split()[-1].lower():
                tercih_puani += 10
        
        # 3. Yaş uygunluk bonus (%10)
        yas_puani = 0
        if yas:
            if yas < 25 and 'genç' in kitap.get('neden', '').lower():
                yas_puani += 8
            elif yas >= 25 and 'klasik' in kitap.get('tur', '').lower():
                yas_puani += 10
        
        # 4. Çeşitlilik ve rastgelelik (%10)
        ceситlilik_puani = random.randint(1, 10)
        
        # Toplam puan hesaplama
        toplam_puan = notlar_puani + tercih_puani + yas_puani + ceситlilik_puani
        kitap['puan'] = round(toplam_puan, 2)
    
    # Puana göre sırala
    return sorted(kitaplar, key=lambda x: x.get('puan', 0), reverse=True)

def calculate_film_similarity_scores(filmler, kullanici_filmleri, notlar):
    scored_filmler = []
    
    for film in filmler:
        # Gerekli anahtarların varlığını kontrol et
        if not all(key in film for key in ['baslik', 'tur']):
            continue
            
        score = 0
        
        # Ek notlar en önemli faktör
        if notlar and notlar.strip():
            notlar_lower = notlar.lower()
            film_tema = ' '.join(film.get('tema', [])).lower()
            film_yonetmen_tarzi = film.get('yonetmen_tarzi', '').lower()
            film_neden = film.get('neden', '').lower()
            
            notlar_kelimeleri = notlar_lower.split()
            for kelime in notlar_kelimeleri:
                if kelime in film_tema:
                    score += 15
                if kelime in film_yonetmen_tarzi:
                    score += 10
                if kelime in film_neden:
                    score += 20
                if kelime in film['baslik'].lower():
                    score += 25
        
        # Tema benzerliği
        for user_film in kullanici_filmleri:
            user_film_lower = user_film.lower()
            if any(tema in user_film_lower for tema in film.get('tema', [])):
                score += 5
        
        # Rastgele çeşitlilik
        import random
        score += random.randint(1, 8)
        
        scored_filmler.append((film, score))
    
    # Skora göre sırala
    scored_filmler.sort(key=lambda x: x[1], reverse=True)
    return [film for film, score in scored_filmler]

def calculate_series_similarity_scores(diziler, kullanici_dizileri, notlar):
    scored_diziler = []
    
    for dizi in diziler:
        # Gerekli anahtarların varlığını kontrol et
        if not all(key in dizi for key in ['baslik', 'tur']):
            continue
            
        score = 0
        
        # Ek notlar en önemli faktör
        if notlar and notlar.strip():
            notlar_lower = notlar.lower()
            dizi_tema = ' '.join(dizi.get('tema', [])).lower()
            dizi_yapimci_tarzi = dizi.get('yapimci_tarzi', '').lower()
            dizi_neden = dizi.get('neden', '').lower()
            
            notlar_kelimeleri = notlar_lower.split()
            for kelime in notlar_kelimeleri:
                if kelime in dizi_tema:
                    score += 15
                if kelime in dizi_yapimci_tarzi:
                    score += 10
                if kelime in dizi_neden:
                    score += 20
                if kelime in dizi['baslik'].lower():
                    score += 25
        
        # Tema benzerliği
        for user_dizi in kullanici_dizileri:
            user_dizi_lower = user_dizi.lower()
            if any(tema in user_dizi_lower for tema in dizi.get('tema', [])):
                score += 5
        
        # Rastgele çeşitlilik
        import random
        score += random.randint(1, 8)
        
        scored_diziler.append((dizi, score))
    
    # Skora göre sırala
    scored_diziler.sort(key=lambda x: x[1], reverse=True)
    return [dizi for dizi, score in scored_diziler]

def calculate_music_similarity_scores(muzikler, kullanici_muzikleri, notlar):
    """Müzik benzerlik skorları"""
    scored_muzikler = []
    
    for muzik in muzikler:
        # Gerekli anahtarların varlığını kontrol et
        if not all(key in muzik for key in ['baslik', 'tur']):
            continue
            
        score = 0
        
        # Ek notlar en önemli faktör
        if notlar and notlar.strip():
            notlar_lower = notlar.lower()
            muzik_tema = ' '.join(muzik.get('tema', [])).lower()
            muzik_sanatci_tarzi = muzik.get('sanatci_tarzi', '').lower()
            muzik_neden = muzik.get('neden', '').lower()
            
            notlar_kelimeleri = notlar_lower.split()
            for kelime in notlar_kelimeleri:
                if kelime in muzik_tema:
                    score += 15
                if kelime in muzik_sanatci_tarzi:
                    score += 10
                if kelime in muzik_neden:
                    score += 20
                if kelime in muzik['baslik'].lower():
                    score += 25
        
        # Tema benzerliği
        for user_muzik in kullanici_muzikleri:
            user_muzik_lower = user_muzik.lower()
            if any(tema in user_muzik_lower for tema in muzik.get('tema', [])):
                score += 5
        
        # Rastgele çeşitlilik
        import random
        score += random.randint(1, 8)
        
        scored_muzikler.append((muzik, score))
    
    # Skora göre sırala
    scored_muzikler.sort(key=lambda x: x[1], reverse=True)
    return [muzik for muzik, score in scored_muzikler]

# ============= VERİTABANI FONKSİYONLARI =============

def get_all_books_database():
    """Kitap veritabanı - API hazır olduğunda JSON dosyasından okuyacak"""
    try:
        # JSON dosyasından oku (eğer varsa)
        json_path = os.path.join(os.path.dirname(__file__), 'data', 'books.json')
        
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                books = json.load(f)
                app.logger.info(f"JSON'dan {len(books)} kitap yüklendi")
                return books
        
        # JSON yoksa manuel veri (API entegrasyonuna kadar)
        app.logger.warning("JSON kitap dosyası bulunamadı, manuel veri kullanılıyor")
        return get_temp_books_for_demo()
        
    except Exception as e:
        app.logger.error(f"Kitap veritabanı yükleme hatası: {e}")
        return get_temp_books_for_demo()

def get_temp_books_for_demo():
    """Gençlere yönelik demo kitapları - API'lar hazır olduğunda silinecek"""
    # ⚠️ Bu veriler API entegrasyonu sonrası silinecek
    app.logger.info("⚠️ Demo modu: Manuel kitap verisi kullanılıyor. API'lar hazır olduğunda otomatik olarak gerçek veriler gelecek.")
    return [
        # Roman - Klasik
        {'baslik': 'Aşk-ı Memnu', 'yazar': 'Halid Ziya Uşaklıgil', 'sayfa': 520, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'yasak', 'drama'], 'yazar_tarzi': 'klasik_roman', 'neden': 'Türk edebiyatının unutulmaz aşk romanı'},
        {'baslik': 'Sinekli Bakkal', 'yazar': 'Halide Edib Adıvar', 'sayfa': 380, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['tarih', 'savaş', 'vatan'], 'yazar_tarzi': 'milli_roman', 'neden': 'Milli mücadele döneminin güçlü romanı'},
        {'baslik': 'Çalıkuşu', 'yazar': 'Reşat Nuri Güntekin', 'sayfa': 450, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['eğitim', 'aşk', 'ideal'], 'yazar_tarzi': 'realist_roman', 'neden': 'Gençlerin en sevdiği klasik roman'},
        {'baslik': 'Mai ve Siyah', 'yazar': 'Halit Ziya Uşaklıgil', 'sayfa': 380, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'gençlik', 'duygusal'], 'yazar_tarzi': 'romantik_roman', 'neden': 'Genç aşkının en güzel anlatımı'},
        
        # Modern Roman
        {'baslik': 'Benim Adım Kırmızı', 'yazar': 'Orhan Pamuk', 'sayfa': 470, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['kimlik', 'aşk', 'gizemli'], 'yazar_tarzi': 'postmodern_roman', 'neden': 'Nobel ödüllü yazardan etkileyici roman'},
        {'baslik': 'Aşka Dair Her Şey', 'yazar': 'Ahmet Ümit', 'sayfa': 320, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'gizem', 'modern'], 'yazar_tarzi': 'modern_roman', 'neden': 'Modern aşk hikayesi'},
        {'baslik': 'Sen de Gitme', 'yazar': 'Peyami Safa', 'sayfa': 280, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'ayrılık', 'duygusal'], 'yazar_tarzi': 'psikolojik_roman', 'neden': 'Duygusal roman severlere'},
        
        # Wattpad Tarzı Genç Romanlar
        {'baslik': 'Aşkın Gücü', 'yazar': 'Zeynep Güner', 'sayfa': 250, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['genç aşkı', 'okul', 'arkadaşlık'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Gençlerin en sevdiği aşk hikayesi'},
        {'baslik': 'Yıldızlar Altında', 'yazar': 'Elif Öztürk', 'sayfa': 180, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['hayal', 'gençlik', 'umut'], 'yazar_tarzi': 'genç_edebiyat', 'neden': 'Hayallerin peşinden koşmaya teşvik eden hikaye'},
        {'baslik': 'Kalbimdeki Sen', 'yazar': 'Ayşe Demir', 'sayfa': 220, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['aşk', 'drama', 'gençlik'], 'yazar_tarzi': 'romantik_drama', 'neden': 'Wattpad\' da en çok okunan hikayelerden'},
        {'baslik': 'Sonsuza Kadar', 'yazar': 'Merve Yıldız', 'sayfa': 300, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['sonsuz aşk', 'drama', 'duygusal'], 'yazar_tarzi': 'drama_romance', 'neden': 'Ağlatan ve güldüren aşk hikayesi'},
        {'baslik': 'Unutulmaz Anılar', 'yazar': 'Canan Erdem', 'sayfa': 190, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['anılar', 'nostalji', 'gençlik'], 'yazar_tarzi': 'nostaljik_roman', 'neden': 'Gençlik anılarını canlandıran hikaye'},
        
        # Genç Kurgu
        {'baslik': 'Zaman Yolcusu Kız', 'yazar': 'Selen Akça', 'sayfa': 280, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['zaman yolculuğu', 'macera', 'gençlik'], 'yazar_tarzi': 'genç_kurgu', 'neden': 'Zaman yolculuğu temalı heyecenli hikaye'},
        {'baslik': 'Rüya Dünyası', 'yazar': 'Deniz Kaya', 'sayfa': 240, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['rüya', 'macera', 'gizemli'], 'yazar_tarzi': 'hayal_kurgu', 'neden': 'Rüya dünyasında geçen büyülü macera'},
        
        # Polisiye/Gerilim (Gençlere Uygun)
        {'baslik': 'Gizli Koda', 'yazar': 'Emre Taş', 'sayfa': 260, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['gizem', 'teknoloji', 'gençlik'], 'yazar_tarzi': 'genç_gerilim', 'neden': 'Teknoloji ve gizem karışımı'},
        {'baslik': 'Kayıp Mesajlar', 'yazar': 'Burcu Akgün', 'sayfa': 200, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['gizem', 'arkadaşlık', 'macera'], 'yazar_tarzi': 'macera_roman', 'neden': 'Arkadaşlarla birlikte çözülen gizem'},
        
        # Kişisel Gelişim (Gençlere Yönelik)
        {'baslik': 'Kendini Keşfet', 'yazar': 'Ayşe Gürel', 'sayfa': 180, 'tur': 'Kişisel Gelişim', 'yas_uygun': True, 'tema': ['kendini tanıma', 'gençlik', 'motivasyon'], 'yazar_tarzi': 'genç_gelişim', 'neden': 'Gençlerin kendini keşfetmesi için'},
        {'baslik': 'Hayallerinin Peşinde', 'yazar': 'Murat Erdoğan', 'sayfa': 220, 'tur': 'Kişisel Gelişim', 'yas_uygun': True, 'tema': ['hayal', 'hedef', 'başarı'], 'yazar_tarzi': 'motivasyon', 'neden': 'Hayallerini gerçekleştirmek isteyen gençler için'}
    ]

def get_all_films_database():
    """Film veritabanı"""
    return [
        # Aksiyon
        {'baslik': 'The Dark Knight', 'yonetmen': 'Christopher Nolan', 'dakika': 152, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['super kahraman', 'adalet', 'kaos'], 'yonetmen_tarzi': 'karmaşık_anlatım', 'neden': 'Batman ve Joker arasındaki psikolojik savaş'},
        {'baslik': 'Mad Max: Fury Road', 'yonetmen': 'George Miller', 'dakika': 120, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['post-apokaliptik', 'araba', 'güçlü kadın'], 'yonetmen_tarzi': 'görsel_aksiyon', 'neden': 'Nefes kesen araba kovalamacaları'},
        {'baslik': 'John Wick', 'yonetmen': 'Chad Stahelski', 'dakika': 101, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['intikam', 'suikastçı', 'köpek'], 'yonetmen_tarzi': 'stilize_aksiyon', 'neden': 'Köpeği için intikam alan profesyonel suikastçı'},
        
        # Romantik
        {'baslik': 'The Notebook', 'yonetmen': 'Nick Cassavetes', 'dakika': 123, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['aşk', 'anılar', 'yaşlılık'], 'yonetmen_tarzi': 'duygusal_romantik', 'neden': 'Ömür boyu süren büyük aşk hikayesi'},
        {'baslik': 'Titanic', 'yonetmen': 'James Cameron', 'dakika': 194, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['aşk', 'trajedi', 'gemi'], 'yonetmen_tarzi': 'epik_romantik', 'neden': 'Trajik gemi kazasında doğan büyük aşk'},
        {'baslik': 'La La Land', 'yonetmen': 'Damien Chazelle', 'dakika': 128, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['müzik', 'hayaller', 'Los Angeles'], 'yonetmen_tarzi': 'müzikal_romantik', 'neden': 'Müzik ve hayaller üzerine modern aşk hikayesi'},
        
        # Komedi
        {'baslik': 'The Hangover', 'yonetmen': 'Todd Phillips', 'dakika': 100, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['Las Vegas', 'parti', 'dostluk'], 'yonetmen_tarzi': 'parti_komedisi', 'neden': 'Las Vegas\'ta unutulan gece komedisi'},
        {'baslik': 'Groundhog Day', 'yonetmen': 'Harold Ramis', 'dakika': 101, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['zaman döngüsü', 'aşk', 'değişim'], 'yonetmen_tarzi': 'felsefi_komedi', 'neden': 'Aynı günü tekrar yaşama komedisi'},
        
        # Drama
        {'baslik': 'The Shawshank Redemption', 'yonetmen': 'Frank Darabont', 'dakika': 142, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['hapishane', 'umut', 'dostluk'], 'yonetmen_tarzi': 'duygusal_drama', 'neden': 'Hapishane hayatı ve umudun gücü'},
        {'baslik': 'Forrest Gump', 'yonetmen': 'Robert Zemeckis', 'dakika': 142, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['hayat', 'aşk', 'tarih'], 'yonetmen_tarzi': 'yaşam_draması', 'neden': 'Saf adamın hayat yolculuğu'},
        
        # Bilim Kurgu
        {'baslik': 'Inception', 'yonetmen': 'Christopher Nolan', 'dakika': 148, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['rüya', 'zihin', 'gerçeklik'], 'yonetmen_tarzi': 'karmaşık_anlatım', 'neden': 'Rüya içinde rüya konsepti'},
        {'baslik': 'The Matrix', 'yonetmen': 'Wachowski Sisters', 'dakika': 136, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['sanal gerçeklik', 'felsefe', 'aksiyon'], 'yonetmen_tarzi': 'felsefi_aksiyon', 'neden': 'Gerçeklik sorgulaması ve aksiyon'}
    ]

def get_all_series_database():
    """Dizi veritabanı"""
    return [
        # Drama
        {'baslik': 'Breaking Bad', 'yaratici': 'Vince Gilligan', 'sezon': 5, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['uyuşturucu', 'dönüşüm', 'aile'], 'yapimci_tarzi': 'karanlık_drama', 'neden': 'Kimya öğretmeninin uyuşturucu baronuna dönüşümü'},
        {'baslik': 'The Crown', 'yaratici': 'Peter Morgan', 'sezon': 6, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['kraliyet', 'tarih', 'politika'], 'yapimci_tarzi': 'tarihsel_drama', 'neden': 'İngiliz kraliyet ailesinin modern tarihi'},
        {'baslik': 'Stranger Things', 'yaratici': 'Duffer Brothers', 'sezon': 4, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['80ler', 'supernatural', 'dostluk'], 'yapimci_tarzi': 'nostaljik_drama', 'neden': '80ler nostaljisi ve supernatural gizem'},
        
        # Komedi
        {'baslik': 'Friends', 'yaratici': 'David Crane', 'sezon': 10, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['dostluk', 'New York', 'aşk'], 'yapimci_tarzi': 'sitcom', 'neden': 'Altı dostun New York maceraları'},
        {'baslik': 'The Office', 'yaratici': 'Greg Daniels', 'sezon': 9, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['iş yeri', 'mockumentary', 'aşk'], 'yapimci_tarzi': 'mockumentary_komedi', 'neden': 'İş yerindeki komik durumlar'},
        {'baslik': 'Brooklyn Nine-Nine', 'yaratici': 'Dan Goor', 'sezon': 8, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['polis', 'dostluk', 'komedi'], 'yapimci_tarzi': 'iş_yeri_komedisi', 'neden': 'Polis karakolunda komik durumlar'},
        
        # Fantastik
        {'baslik': 'Game of Thrones', 'yaratici': 'David Benioff', 'sezon': 8, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['ejder', 'savaş', 'politik'], 'yapimci_tarzi': 'epik_fantastik', 'neden': 'Politik entrika ve karanlık fantastik dünya'},
        {'baslik': 'The Witcher', 'yaratici': 'Lauren Schmidt', 'sezon': 3, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['canavar', 'büyücü', 'macera'], 'yapimci_tarzi': 'karanlık_fantastik', 'neden': 'Canavar avcısı ve karanlık büyü'},
        
        # Gerilim
        {'baslik': 'Sherlock', 'yaratici': 'Mark Gatiss', 'sezon': 4, 'tur': 'Gerilim', 'yas_uygun': True, 'tema': ['dedektif', 'gizem', 'modern'], 'yapimci_tarzi': 'modern_polisiye', 'neden': 'Modern zamanda Sherlock Holmes'},
        {'baslik': 'Mindhunter', 'yaratici': 'Joe Penhall', 'sezon': 2, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['seri katil', 'psikoloji', 'FBI'], 'yapimci_tarzi': 'psikolojik_gerilim', 'neden': 'FBI\'ın seri katil profilleme çalışması'}
    ]

def get_all_music_database():
    """Müzik veritabanı - Türkçe ağırlıklı"""
    return [
        # Pop Türkçe
        {'baslik': 'Aşk', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2001, 'tema': ['aşk', 'romantik'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True, 'neden': 'Türk pop müziğinin klasiği'},
        {'baslik': 'Şımarık', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1997, 'tema': ['eğlence', 'dans'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True, 'neden': 'Dansa eden hit şarkı'},
        {'baslik': 'Gülpembe', 'sanatci': 'Barış Manço', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 1985, 'tema': ['aşk', 'nostalji'], 'sanatci_tarzi': 'anadolu_rock', 'yas_uygun': True, 'neden': 'Türk müziğinin efsane aşk şarkısı'},
        {'baslik': 'Kış Güneşi', 'sanatci': 'Teoman', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 2001, 'tema': ['melankolik', 'aşk'], 'sanatci_tarzi': 'alternative_rock', 'yas_uygun': True, 'neden': 'Kış mevsiminin en güzel şarkısı'},
        {'baslik': 'İstanbul', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1995, 'tema': ['şehir', 'nostalji'], 'sanatci_tarzi': 'legend', 'yas_uygun': True, 'neden': 'İstanbul aşkının müzikal anlatımı'},
        
        # Türkçe Rap/Hip Hop
        {'baslik': 'Susamam', 'sanatci': 'Şanışer', 'tur': 'Rap', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['protesto', 'toplum', 'eleştiri'], 'sanatci_tarzi': 'conscious_rap', 'yas_uygun': True, 'neden': 'Sosyal eleştiri ve protesto rap'},
        {'baslik': 'Yeraltı', 'sanatci': 'Ceza', 'tur': 'Rap', 'dil': 'Türkçe', 'yil': 2004, 'tema': ['sokak', 'gerçek', 'yaşam'], 'sanatci_tarzi': 'turkish_rap', 'yas_uygun': True, 'neden': 'Türkçe rap\'in klasiği'},
        {'baslik': 'Beatcoin', 'sanatci': 'Ezhel', 'tur': 'Rap', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['modern', 'teknoloji', 'para'], 'sanatci_tarzi': 'trap_rap', 'yas_uygun': True, 'neden': 'Modern Türk trap rap'},
        {'baslik': 'Flow', 'sanatci': 'Norm Ender', 'tur': 'Rap', 'dil': 'Türkçe', 'yil': 2016, 'tema': ['gençlik', 'flow', 'beceri'], 'sanatci_tarzi': 'skill_rap', 'yas_uygun': True, 'neden': 'Türk rap\'inin flow krali'},
        {'baslik': 'Ben Bu Şarkıyı Sana Yaptım', 'sanatci': 'Sagopa Kajmer', 'tur': 'Rap', 'dil': 'Türkçe', 'yil': 2008, 'tema': ['aşk', 'duygusal rap', 'ilişki'], 'sanatci_tarzi': 'emotional_rap', 'yas_uygun': True, 'neden': 'Duygusal rap\'in en güzel örneği'},
        {'baslik': 'Kafam Kaşınmasın', 'sanatci': 'Hidra', 'tur': 'Rap', 'dil': 'Türkçe', 'yil': 2019, 'tema': ['gençlik', 'eğlence', 'parti'], 'sanatci_tarzi': 'party_rap', 'yas_uygun': True, 'neden': 'Gençlerin parti şarkısı'},
        
        # İngilizce Rap Klasikleri
        {'baslik': 'Lose Yourself', 'sanatci': 'Eminem', 'tur': 'Rap', 'dil': 'İngilizce', 'yil': 2002, 'tema': ['motivasyon', 'fırsat', 'başarı'], 'sanatci_tarzi': 'motivational_rap', 'yas_uygun': True, 'neden': 'Motivasyon veren en iyi rap şarkısı'},
        {'baslik': 'HUMBLE.', 'sanatci': 'Kendrick Lamar', 'tur': 'Rap', 'dil': 'İngilizce', 'yil': 2017, 'tema': ['alçakgönüllülük', 'modern', 'conscious'], 'sanatci_tarzi': 'conscious_rap', 'yas_uygun': True, 'neden': 'Modern rap\'in zirvesi'},
        
        # İngilizce Pop/Rock Klasikler
        {'baslik': 'Bohemian Rhapsody', 'sanatci': 'Queen', 'tur': 'Rock', 'dil': 'İngilizce', 'yil': 1975, 'tema': ['epik', 'opera'], 'sanatci_tarzi': 'classic_rock', 'yas_uygun': True, 'neden': 'Rock müziğin en epik eserlerinden biri'},
        {'baslik': 'Hotel California', 'sanatci': 'Eagles', 'tur': 'Rock', 'dil': 'İngilizce', 'yil': 1976, 'tema': ['kaliforniya', 'gizem', 'gitar'], 'sanatci_tarzi': 'soft_rock', 'yas_uygun': True, 'neden': 'Efsanevi gitar solosu ve atmosferik hikaye'},
        {'baslik': 'Imagine', 'sanatci': 'John Lennon', 'tur': 'Pop', 'dil': 'İngilizce', 'yil': 1971, 'tema': ['barış', 'hayal', 'umut'], 'sanatci_tarzi': 'peaceful_pop', 'yas_uygun': True, 'neden': 'Barış ve umut mesajı veren ikonik şarkı'},
        {'baslik': 'Yesterday', 'sanatci': 'The Beatles', 'tur': 'Pop', 'dil': 'İngilizce', 'yil': 1965, 'tema': ['nostalji', 'aşk', 'melodi'], 'sanatci_tarzi': 'beatles_pop', 'yas_uygun': True, 'neden': 'En çok cover yapılan şarkılardan biri'},
        {'baslik': 'Billie Jean', 'sanatci': 'Michael Jackson', 'tur': 'Pop', 'dil': 'İngilizce', 'yil': 1982, 'tema': ['dans', 'ritim', 'hikaye'], 'sanatci_tarzi': 'pop_king', 'yas_uygun': True, 'neden': 'Pop müziğinin kralı'},
        
        # Elektronik/Dance
        {'baslik': 'One More Time', 'sanatci': 'Daft Punk', 'tur': 'Elektronik', 'dil': 'İngilizce', 'yil': 2000, 'tema': ['dans', 'robot', 'parti'], 'sanatci_tarzi': 'french_house', 'yas_uygun': True, 'neden': 'French house klasiği'},
        {'baslik': 'Levels', 'sanatci': 'Avicii', 'tur': 'Elektronik', 'dil': 'İngilizce', 'yil': 2011, 'tema': ['enerji', 'festival', 'dans'], 'sanatci_tarzi': 'progressive_house', 'yas_uygun': True, 'neden': 'EDM festivallerinin anthem\'i'},
        
        # R&B/Soul
        {'baslik': 'Respect', 'sanatci': 'Aretha Franklin', 'tur': 'R&B', 'dil': 'İngilizce', 'yil': 1967, 'tema': ['güçlü kadın', 'saygı'], 'sanatci_tarzi': 'soul_queen', 'yas_uygun': True, 'neden': 'Kadın hakları anthem\'i'},
        {'baslik': 'What\'s Going On', 'sanatci': 'Marvin Gaye', 'tur': 'R&B', 'dil': 'İngilizce', 'yil': 1971, 'tema': ['sosyal', 'barış', 'siyah'], 'sanatci_tarzi': 'conscious_soul', 'yas_uygun': True, 'neden': 'Sosyal bilinç ve barış mesajı'}
    ]

# ============= GOOGLE LOGIN =============

@app.route('/google_giris')
def google_giris():
    if not config.has_google_oauth:
        return render_template('index.html', 
                             hata="Google ile giriş şu anda kullanılamıyor. Lütfen normal giriş yapın.", 
                             info="Google OAuth yapılandırması eksik.")
    
    try:
        google_provider_cfg = get_google_provider_cfg()
        authorization_endpoint = google_provider_cfg["authorization_endpoint"]
        
        # Gençlere yönelik uygulama için ek kapsamlar
        request_uri = client.prepare_request_uri(
            authorization_endpoint,
            redirect_uri=request.base_url + "/callback",
            scope=["openid", "email", "profile"],
            # Gençlere yönelik ek güvenlik
            state="listoria_secure_state"
        )
        return redirect(request_uri)
    except Exception as e:
        app.logger.error(f"Google login hatası: {str(e)}")
        return render_template('index.html', hata="Google ile giriş yapılamadı. Lütfen tekrar deneyin.")

@app.route("/google_giris/callback")
def callback():
    try:
        code = request.args.get("code")
        google_provider_cfg = get_google_provider_cfg()
        token_endpoint = google_provider_cfg["token_endpoint"]
        
        token_url, headers, body = client.prepare_token_request(
            token_endpoint,
            authorization_response=request.url,
            redirect_url=request.base_url,
            client_secret=config.GOOGLE_CLIENT_SECRET
        )
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=(config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET)
        )
        client.parse_request_body_response(json.dumps(token_response.json()))

        userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
        uri, headers, body = client.add_token(userinfo_endpoint)
        userinfo_response = requests.get(uri, headers=headers)
        
        if userinfo_response.json().get("email_verified"):
            users_email = userinfo_response.json()["email"]
            users_name = userinfo_response.json()["name"]
            
            # Yaş kontrolü için kullanıcıdan doğum tarihi isteyebiliriz
            # Ama şimdilik Google hesabı olanların 13+ olduğunu varsayıyoruz
            
            conn = get_db_connection()
            user_in_db = conn.execute('SELECT 1 FROM kullanicilar WHERE email = ?', (users_email,)).fetchone()
            
            if user_in_db:
                session['logged_in'] = True
                session['kullanici_adi'] = users_name
                conn.close()
                app.logger.info(f"Google ile giriş başarılı: {users_email}")
                return redirect(url_for('dashboard'))
            else:
                # Yeni kullanıcı - varsayılan doğum tarihi (gençler için uygun)
                conn.execute('INSERT INTO kullanicilar (email, kullanici_adi, sifre, dogum_tarihi) VALUES (?, ?, ?, ?)', 
                           (users_email, users_name, 'google_login', '2000-01-01'))
                conn.commit()
                session['logged_in'] = True
                session['kullanici_adi'] = users_name
                conn.close()
                app.logger.info(f"Yeni Google kullanıcısı kaydedildi: {users_email}")
                return redirect(url_for('dashboard'))
        else:
            return render_template('index.html', hata="Google hesabı doğrulanamadı.")
    except Exception as e:
        app.logger.error(f"Google callback hatası: {str(e)}")
        return render_template('index.html', hata="Google ile giriş tamamlanamadı. Lütfen tekrar deneyin.")

# ============= API TEST ROUTE =============

@app.route('/api-test')
def api_test():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    test_results = {
        'google_books': 'Kapalı',
        'tmdb_movies': 'Kapalı',
        'tmdb_tv': 'Kapalı',
        'lastfm': 'Kapalı',
        'hugging_face': 'Kapalı'
    }
    
    # Google Books API Test
    if config.has_google_books_api:
        try:
            books = fetch_google_books_api('harry potter', 1)
            test_results['google_books'] = f'Aktif - {len(books)} sonuç'
        except Exception as e:
            test_results['google_books'] = f'Hata: {str(e)[:50]}'
    
    # TMDB Movies API Test
    if config.has_tmdb_api:
        try:
            movies = fetch_tmdb_movies_api('avengers', 1)
            test_results['tmdb_movies'] = f'Aktif - {len(movies)} sonuç'
        except Exception as e:
            test_results['tmdb_movies'] = f'Hata: {str(e)[:50]}'
        
        # TMDB TV Test
        try:
            series = fetch_tmdb_tv_api('breaking bad', 1)
            test_results['tmdb_tv'] = f'Aktif - {len(series)} sonuç'
        except Exception as e:
            test_results['tmdb_tv'] = f'Hata: {str(e)[:50]}'
    
    # Last.fm API Test
    if config.has_lastfm_api:
        try:
            tracks = fetch_lastfm_music_api('bohemian rhapsody', 1)
            test_results['lastfm'] = f'Aktif - {len(tracks)} sonuç'
        except Exception as e:
            test_results['lastfm'] = f'Hata: {str(e)[:50]}'
    
    # Hugging Face API Test
    if config.has_hugging_face_api:
        try:
            ai_response = get_huggingface_ai_recommendation('science fiction books', 'book')
            test_results['hugging_face'] = f'Aktif - AI cevap alındı'
        except Exception as e:
            test_results['hugging_face'] = f'Hata: {str(e)[:50]}'
    
    return render_template('api-test.html', test_results=test_results)

# ============= ŞİFRE SIFIRLAMA =============

@app.route('/sifremi-unuttum')
def sifremi_unuttum():
    return render_template('sifremi-unuttum.html')

@app.route('/sifre-sifirla', methods=['POST'])
def sifre_sifirla():
    email = request.form['email']
    
    if not email:
        return render_template('sifremi-unuttum.html', hata="Lütfen bir e-posta adresi giriniz.")
    
    conn = get_db_connection()
    kullanici = conn.execute('SELECT 1 FROM kullanicilar WHERE email = ?', (email,)).fetchone()
    conn.close()

    if not kullanici:
        return render_template('sifremi-unuttum.html', hata="Bu e-posta adresi sistemimizde kayıtlı değil.")
    
    sifre_sifirla_kodu = str(random.randint(100000, 999999))
    password_reset_codes[email] = sifre_sifirla_kodu
    
    subject = "Şifre Sıfırlama Kodu"
    body = f"Şifrenizi sıfırlamak için aşağıdaki kodu kullanın: {sifre_sifirla_kodu}"
    
    if send_email(email, subject, body):
        return redirect(url_for('yeni_sifre_sayfasi', email=email))
    else:
        return render_template('sifremi-unuttum.html', hata="E-posta gönderimi başarısız. Lütfen e-posta adresinizi kontrol edin.")

@app.route('/yeni-sifre-sayfasi')
def yeni_sifre_sayfasi():
    email = request.args.get('email')
    if not email or email not in password_reset_codes:
        return redirect(url_for('sifremi_unuttum'))
    return render_template('yeni-sifre.html', email=email)

@app.route('/yeni-sifre', methods=['POST'])
def yeni_sifre():
    email = request.form['email']
    girilen_kod = request.form['kod']
    yeni_sifre = request.form['yeni_sifre']

    if email in password_reset_codes and password_reset_codes[email] == girilen_kod:
        conn = get_db_connection()
        conn.execute('UPDATE kullanicilar SET sifre = ? WHERE email = ?', (yeni_sifre, email))
        conn.commit()
        conn.close()
        
        del password_reset_codes[email]
        
        return redirect(url_for('home'))
    else:
        return redirect(url_for('sifremi_unuttum'))

# ============= SPOTIFY PLAYLIST ROUTE =============

@app.route('/spotify-playlist-olustur', methods=['POST'])
def spotify_playlist_olustur():
    if 'logged_in' not in session:
        return jsonify({'error': 'Giriş yapmanız gerekiyor'}), 401
    
    try:
        data = request.get_json()
        sarkilar = data.get('sarkilar', [])
        tur = data.get('tur', 'Karışık')
        
        if not sarkilar:
            return jsonify({'error': 'Şarkı listesi boş'}), 400
        
        playlist_data = create_spotify_playlist(sarkilar, tur)
        return jsonify(playlist_data)
        
    except Exception as e:
        app.logger.error(f"Playlist oluşturma API hatası: {str(e)}")
        return jsonify({'error': 'Playlist oluşturulamadı'}), 500

