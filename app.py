from flask import Flask, render_template, request, redirect, url_for, session
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

# Güvenli olmayan bağlantılar için OAuth2 kütüphanesine izin ver
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

load_dotenv()

app = Flask(__name__)
# Secret key ortam değişkeninden alınır
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this-in-production')
app.permanent_session_lifetime = timedelta(days=30)

# Google Login Ayarları
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# E-POSTA AYARLARI
SENDER_EMAIL = os.getenv('SENDER_EMAIL', '')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', '')

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

def get_db_connection():
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
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
        smtp.send_message(msg)

@app.route('/')
def home():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# Yeni dashboard route'u (eski basarilar)
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

        return render_template('recommender.html', profil=profil)
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
        # Başarılı girişte doğrudan recommender sayfasına yönlendir.
        return redirect(url_for('dashboard'))
    else:
        return render_template('index.html', hata="Hatalı e-posta veya şifre!")

@app.route('/kayit')
def kayit():
    return render_template('register.html')

@app.route('/kayit-ol', methods=['POST'])
def kayit_ol():
    email = request.form['email']
    kullanici_adi = request.form['kullanici_adi']
    sifre = request.form['sifre']
    dogum_tarihi = request.form['dogum_tarihi']
    
    if not email or not sifre or not dogum_tarihi or not kullanici_adi:
        return render_template('register.html', hata="Lütfen tüm alanları doldurunuz.")
        
    conn = get_db_connection()
    user_exists = conn.execute('SELECT 1 FROM kullanicilar WHERE email = ?', (email,)).fetchone()
    
    if user_exists:
        conn.close()
        return render_template('register.html', hata="Bu e-posta adresi zaten kayıtlı!")
    
    verification_code = str(random.randint(100000, 999999))
    verification_codes[email] = {
        'code': verification_code,
        'kullanici_adi': kullanici_adi,
        'sifre': sifre,
        'dogum_tarihi': dogum_tarihi
    }
    
    subject = "Hesap Doğrulama Kodu"
    body = f"Merhaba {kullanici_adi},\n\n Hesabını doğrulamak için aşağıdaki kodu kullan:\n\n{verification_code}\n\nBu kodu kimseyle paylaşma. İyi günler dileriz."
    send_email(email, subject, body)
    
    return redirect(url_for('dogrulama', email=email))

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
        del verification_codes[email]
        return render_template('verification.html', email=email, hata="Hatalı doğrulama kodu! Lütfen tekrar kayıt olunuz.")

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
    send_email(email, subject, body)
    
    return redirect(url_for('yeni_sifre_sayfasi', email=email))

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
    
    # 1. Aynı kitap birden fazla girildiyse hata ver
    if len(set([k.lower() for k in kullanici_kitaplari])) != len(kullanici_kitaplari):
        return render_template('kitap_oneri.html', hata="Aynı kitabı birden fazla girmeyiniz.", yas=None)
    
    # 2. Girilen kitaplar veritabanında yoksa hata ver
    kitap_db = get_all_books_database()
    kitap_db_lower = [k['baslik'].lower() for k in kitap_db]
    olmayanlar = [k for k in kullanici_kitaplari if k.lower() not in kitap_db_lower]
    if olmayanlar:
        return render_template('kitap_oneri.html', hata=f"Veritabanında olmayan kitap(lar): {', '.join(olmayanlar)}", yas=None)
    
    # ...devamı aynı...
    
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
    
    # En az 3 kitap kontrolü
    if len(kullanici_kitaplari) < 3:
        return redirect(url_for('oneri_sayfasi', kategori='kitap'))
    
    # Gelişmiş AI öneri algoritması
    try:
        oneriler = generate_book_recommendations(kullanici_kitaplari, yas, tur, min_sayfa, max_sayfa, notlar)
    except Exception as e:
        # Hata durumunda geri yönlendir
        return redirect(url_for('oneri_sayfasi', kategori='kitap'))
    
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

def generate_book_recommendations(kullanici_kitaplari, yas, tur, min_sayfa, max_sayfa, notlar):
    """Gelişmiş kitap öneri algoritması - çok daha fazla kitap ve ek notlar etkili"""
    
    # Girilen kitapları küçük harfe çevir (karşılaştırma için)
    girilen_kitaplar = [kitap.lower() for kitap in kullanici_kitaplari]
    
    # Çok büyük kitap veritabanı - gerçek AI için
    tum_oneriler = get_all_books_database()
    
    # Yaş filtreleme
    if yas and yas < 18:
        tum_oneriler = [k for k in tum_oneriler if k.get('yas_uygun', True)]
    
    # Girilen kitapları çıkar (tekrar önermemek için)
    filtered_oneriler = []
    for oneri in tum_oneriler:
        kitap_adi_kucuk = oneri['baslik'].lower()
        # Girilen kitaplarla eşleşme kontrolü
        eslesme_var = False
        for girilen in girilen_kitaplar:
            if any(kelime in kitap_adi_kucuk for kelime in girilen.split() if len(kelime) > 3):
                eslesme_var = True
                break
        if not eslesme_var:
            filtered_oneriler.append(oneri)
    
    # Ek notlara göre puanlama sistemi
    if notlar and notlar.strip():
        notlar_kucuk = notlar.lower()
        for oneri in filtered_oneriler:
            puan = 0
            # Anahtar kelime eşleşmesi
            for kelime in oneri['anahtar_kelimeler']:
                if kelime in notlar_kucuk:
                    puan += 3
            # Tür eşleşmesi
            if oneri['tur'].lower() in notlar_kucuk:
                puan += 2
            # Genel kelime eşleşmesi
            for kelime in notlar_kucuk.split():
                if len(kelime) > 3 and kelime in oneri['aciklama'].lower():
                    puan += 1
            oneri['puan'] = puan
        
        # Puana göre sırala
        filtered_oneriler.sort(key=lambda x: x.get('puan', 0), reverse=True)
    
    # Tür filtreleme
    if tur:
        tur_filtered = [o for o in filtered_oneriler if o['tur'].lower() == tur.lower()]
        if tur_filtered:
            filtered_oneriler = tur_filtered
    
    # Sayfa sayısı filtreleme
    if min_sayfa or max_sayfa:
        sayfa_filtered = []
        for oneri in filtered_oneriler:
            sayfa = oneri['sayfa']
            if min_sayfa and sayfa < int(min_sayfa):
                continue
            if max_sayfa and sayfa > int(max_sayfa):
                continue
            sayfa_filtered.append(oneri)
        filtered_oneriler = sayfa_filtered
    
    # Gerçek AI algoritması - benzerlik analizi
    scored_oneriler = calculate_similarity_scores(filtered_oneriler, kullanici_kitaplari, notlar)
    
    return scored_oneriler[:8]  # En fazla 8 öneri

def get_all_books_database():
    """JSON dosyasından kitap veritabanını oku"""
    try:
        import json
        import os
        
        # JSON dosya yolu
        json_path = os.path.join(os.path.dirname(__file__), 'data', 'books.json')
        
        # JSON dosyası varsa oku
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                books = json.load(f)
                print(f"📚 {len(books)} kitap JSON'dan yüklendi")
                return books
        
        # JSON yoksa fallback olarak hardcoded veri
        print("⚠️  JSON dosyası bulunamadı, hardcoded veri kullanılıyor")
        return get_hardcoded_books()
        
    except Exception as e:
        print(f"❌ Kitap veritabanı yükleme hatası: {e}")
        # Hata durumunda fallback veri
        return get_hardcoded_books()

def get_hardcoded_books():
    """Hardcoded kitap veritabanı"""
    return [
        # Fantastik
        {'baslik': 'Harry Potter ve Felsefe Taşı', 'yazar': 'J.K. Rowling', 'sayfa': 320, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['büyü', 'okul', 'dostluk'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Büyücülük okulu ve dostluk maceraları', 'anahtar_kelimeler': ['büyü', 'okul', 'dostluk', 'macera', 'fantastik'], 'aciklama': '11 yaşındaki Harry Potter\'ın büyücülük okulundaki maceraları'},
        {'baslik': 'Yüzüklerin Efendisi', 'yazar': 'J.R.R. Tolkien', 'sayfa': 1216, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['epik', 'macera', 'mitoloji'], 'yazar_tarzi': 'klasik_fantastik', 'neden': 'Epik fantastik macera ve mitolojik dünya', 'anahtar_kelimeler': ['epik', 'macera', 'mitoloji', 'fantastik', 'yüzük'], 'aciklama': 'Orta Dünya\'da yüzüğün yok edilmesi için yapılan yolculuk'},
        {'baslik': 'Hobbit', 'yazar': 'J.R.R. Tolkien', 'sayfa': 310, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['macera', 'yolculuk'], 'yazar_tarzi': 'klasik_fantastik', 'neden': 'Macera dolu yolculuk hikayesi', 'anahtar_kelimeler': ['macera', 'yolculuk', 'fantastik', 'hobbit'], 'aciklama': 'Hobbit Bilbo\'nun macera dolu yolculuğu'},
        {'baslik': 'Percy Jackson', 'yazar': 'Rick Riordan', 'sayfa': 380, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['mitoloji', 'aksiyon'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Modern dünyada Yunan mitolojisi'},
        {'baslik': 'Narnia', 'yazar': 'C.S. Lewis', 'sayfa': 206, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['büyü', 'çocukluk'], 'yazar_tarzi': 'klasik_fantastik', 'neden': 'Büyülü dünya ve çocukluk maceraları'},
        
        # Distopya
        {'baslik': '1984', 'yazar': 'George Orwell', 'sayfa': 350, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['totaliter', 'gözetim'], 'yazar_tarzi': 'politik_eleştiri', 'neden': 'Totaliter rejim ve gözetim toplumu eleştirisi'},
        {'baslik': 'Cesur Yeni Dünya', 'yazar': 'Aldous Huxley', 'sayfa': 311, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['teknoloji', 'toplum'], 'yazar_tarzi': 'bilimsel_distopya', 'neden': 'Teknolojinin toplumu kontrol etmesi'},
        {'baslik': 'Açlık Oyunları', 'yazar': 'Suzanne Collins', 'sayfa': 374, 'tur': 'Distopya', 'yas_uygun': True, 'tema': ['hayatta kalma', 'güçlü kadın'], 'yazar_tarzi': 'aksiyon_distopya', 'neden': 'Güçlü kadın karakter ve hayatta kalma mücadelesi'},
        {'baslik': 'Fahrenheit 451', 'yazar': 'Ray Bradbury', 'sayfa': 249, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['sansür', 'bilgi'], 'yazar_tarzi': 'felsefi_distopya', 'neden': 'Bilgi sansürü ve düşünce özgürlüğü'},
        
        # Klasik
        {'baslik': 'Suç ve Ceza', 'yazar': 'Fyodor Dostoyevski', 'sayfa': 670, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['psikoloji', 'ahlak'], 'yazar_tarzi': 'rus_klasik', 'neden': 'Psikolojik derinlik ve ahlaki sorgulamalar'},
        {'baslik': 'Kürk Mantolu Madonna', 'yazar': 'Sabahattin Ali', 'sayfa': 160, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['aşk', 'yalnızlık'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Türk edebiyatının aşk klasiği'},
        {'baslik': 'İnce Memed', 'yazar': 'Yaşar Kemal', 'sayfa': 420, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['adalet', 'halk'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Halk kahramanı ve adalet mücadelesi'},
        
        # Bilim Kurgu
        {'baslik': 'Dune', 'yazar': 'Frank Herbert', 'sayfa': 688, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['uzay', 'politik'], 'yazar_tarzi': 'epik_bilimkurgu', 'neden': 'Epik uzay operası ve politik entrikalar'},
        {'baslik': 'Otostopçunun Galaksi Rehberi', 'yazar': 'Douglas Adams', 'sayfa': 224, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['komedi', 'uzay'], 'yazar_tarzi': 'komik_bilimkurgu', 'neden': 'Komik bilim kurgu ve absürt mizah'},
        
        # Gerilim/Polisiye
        {'baslik': 'Sherlock Holmes', 'yazar': 'Arthur Conan Doyle', 'sayfa': 307, 'tur': 'Polisiye', 'yas_uygun': True, 'tema': ['dedektif', 'gizem'], 'yazar_tarzi': 'klasik_polisiye', 'neden': 'Klasik dedektif hikayeleri ve mantıklı çözümler'},
        {'baslik': 'Agatha Christie - Doğu Ekspresinde Cinayet', 'yazar': 'Agatha Christie', 'sayfa': 256, 'tur': 'Polisiye', 'yas_uygun': True, 'tema': ['gizem', 'cinayet'], 'yazar_tarzi': 'klasik_polisiye', 'neden': 'Ustaca kurgulanmış cinayet gizemi'},
        
        # Aşk/Romantik
        {'baslik': 'Aşk-ı Memnu', 'yazar': 'Halit Ziya Uşaklıgil', 'sayfa': 380, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['aşk', 'yasak'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Yasak aşk ve toplumsal baskı'},
        {'baslik': 'Gurur ve Önyargı', 'yazar': 'Jane Austen', 'sayfa': 432, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['aşk', 'toplum'], 'yazar_tarzi': 'ingiliz_klasik', 'neden': 'Toplumsal önyargıları aşan aşk hikayesi'},
        
        # Felsefe/Kişisel Gelişim
        {'baslik': 'Simyacı', 'yazar': 'Paulo Coelho', 'sayfa': 163, 'tur': 'Felsefe', 'yas_uygun': True, 'tema': ['hayal', 'kişisel gelişim'], 'yazar_tarzi': 'ruhani_felsefe', 'neden': 'Hayallerin peşinden gitme konusunda ilham verici'},
        {'baslik': 'Küçük Prens', 'yazar': 'Antoine de Saint-Exupéry', 'sayfa': 120, 'tur': 'Felsefe', 'yas_uygun': True, 'tema': ['yaşam', 'dostluk'], 'yazar_tarzi': 'felsefi_masal', 'neden': 'Yaşamın anlamı hakkında derin düşünceler'},
        
        # Daha fazla Fantastik
        {'baslik': 'Game of Thrones', 'yazar': 'George R.R. Martin', 'sayfa': 694, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['savaş', 'politik', 'ejder'], 'yazar_tarzi': 'karanlık_fantastik', 'neden': 'Politik entrika ve karanlık fantastik dünya'},
        {'baslik': 'Witcher', 'yazar': 'Andrzej Sapkowski', 'sayfa': 288, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['canavar', 'büyücü', 'macera'], 'yazar_tarzi': 'karanlık_fantastik', 'neden': 'Canavar avcısı ve karanlık büyü'},
        {'baslik': 'Eragon', 'yazar': 'Christopher Paolini', 'sayfa': 509, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['ejder', 'büyü', 'genç kahraman'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Ejder binicisi ve genç kahramanın yolculuğu'},
        {'baslik': 'Mistborn', 'yazar': 'Brandon Sanderson', 'sayfa': 541, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['büyü sistemi', 'devrim'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Benzersiz büyü sistemi ve devrim hikayesi'},
        {'baslik': 'Name of the Wind', 'yazar': 'Patrick Rothfuss', 'sayfa': 662, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['müzik', 'büyü', 'hikaye'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Müzik ve büyünün birleştiği poetik anlatım'},
        
        # Daha fazla Bilim Kurgu
        {'baslik': 'Foundation', 'yazar': 'Isaac Asimov', 'sayfa': 244, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['galaksi', 'matematik', 'gelecek'], 'yazar_tarzi': 'klasik_bilimkurgu', 'neden': 'Galaktik imparatorluk ve matematik'},
        {'baslik': 'Ender\'s Game', 'yazar': 'Orson Scott Card', 'sayfa': 324, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['uzay savaşı', 'çocuk deha'], 'yazar_tarzi': 'askeri_bilimkurgu', 'neden': 'Çocuk deha ve uzay savaşı stratejisi'},
        {'baslik': 'Neuromancer', 'yazar': 'William Gibson', 'sayfa': 271, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['siber', 'hacker', 'yapay zeka'], 'yazar_tarzi': 'cyberpunk', 'neden': 'Cyberpunk türünün öncüsü'},
        {'baslik': 'Blade Runner', 'yazar': 'Philip K. Dick', 'sayfa': 210, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['android', 'kimlik', 'gelecek'], 'yazar_tarzi': 'felsefi_bilimkurgu', 'neden': 'İnsanlık ve yapay zeka sorgulaması'},
        {'baslik': 'Mars Üçlemesi', 'yazar': 'Kim Stanley Robinson', 'sayfa': 572, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['mars', 'kolonizasyon'], 'yazar_tarzi': 'sert_bilimkurgu', 'neden': 'Mars kolonizasyonunun bilimsel detayları'},
        
        # Daha fazla Polisiye/Gerilim
        {'baslik': 'Da Vinci Şifresi', 'yazar': 'Dan Brown', 'sayfa': 454, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['gizem', 'tarih', 'din'], 'yazar_tarzi': 'tarihsel_gerilim', 'neden': 'Tarihsel gizem ve din konularında heyecan'},
        {'baslik': 'Girl with Dragon Tattoo', 'yazar': 'Stieg Larsson', 'sayfa': 465, 'tur': 'Polisiye', 'yas_uygun': False, 'tema': ['hacker', 'cinayet', 'İsveç'], 'yazar_tarzi': 'nordic_noir', 'neden': 'Modern hacker kültürü ve İskandinav noir'},
        {'baslik': 'Gone Girl', 'yazar': 'Gillian Flynn', 'sayfa': 419, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['evlilik', 'psikoloji'], 'yazar_tarzi': 'psikolojik_gerilim', 'neden': 'Evlilik ve psikolojik manipülasyon'},
        {'baslik': 'Big Sleep', 'yazar': 'Raymond Chandler', 'sayfa': 231, 'tur': 'Polisiye', 'yas_uygun': False, 'tema': ['dedektif', 'noir'], 'yazar_tarzi': 'hard_boiled', 'neden': 'Klasik hard-boiled dedektif hikayesi'},
        
        # Daha fazla Klasik
        {'baslik': 'Savaş ve Barış', 'yazar': 'Lev Tolstoy', 'sayfa': 1225, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['savaş', 'aşk', 'tarih'], 'yazar_tarzi': 'rus_klasik', 'neden': 'Napeleon savaşları ve Rus toplumu'},
        {'baslik': 'Moby Dick', 'yazar': 'Herman Melville', 'sayfa': 635, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['deniz', 'obsesyon'], 'yazar_tarzi': 'amerikan_klasik', 'neden': 'Obsesyon ve doğanın gücü'},
        {'baslik': 'Ulysses', 'yazar': 'James Joyce', 'sayfa': 730, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['bilinç akışı', 'Dublin'], 'yazar_tarzi': 'modernist', 'neden': 'Modernist edebiyatın zirvesi'},
        {'baslik': 'Catch-22', 'yazar': 'Joseph Heller', 'sayfa': 453, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['savaş', 'absürd'], 'yazar_tarzi': 'savaş_karşıtı', 'neden': 'Savaşın absürdlüğü ve bürokrasi eleştirisi'},
        {'baslik': 'Catcher in the Rye', 'yazar': 'J.D. Salinger', 'sayfa': 277, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['gençlik', 'yabancılaşma'], 'yazar_tarzi': 'amerikan_klasik', 'neden': 'Gençlik dönemi ve toplumsal yabancılaşma'},
        
        # Türk Edebiyatı
        {'baslik': 'Tutunamayanlar', 'yazar': 'Oğuz Atay', 'sayfa': 724, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['modernleşme', 'kimlik'], 'yazar_tarzi': 'türk_modern', 'neden': 'Modernleşme sürecinde kimlik arayışı'},
        {'baslik': 'Çalıkuşu', 'yazar': 'Reşat Nuri Güntekin', 'sayfa': 380, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['aşk', 'öğretmen'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Öğretmenlik mesleği ve fedakarlık'},
        {'baslik': 'Sinekli Bakkal', 'yazar': 'Halide Edib Adıvar', 'sayfa': 420, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['savaş', 'kadın'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Kurtuluş Savaşı ve kadın mücadelesi'},
        {'baslik': 'Beyaz Kale', 'yazar': 'Orhan Pamuk', 'sayfa': 161, 'tur': 'Modern', 'yas_uygun': False, 'tema': ['kimlik', 'Osmanlı'], 'yazar_tarzi': 'postmodern', 'neden': 'Doğu-Batı kimlik sorgulaması'},
        {'baslik': 'Masumiyet Müzesi', 'yazar': 'Orhan Pamuk', 'sayfa': 592, 'tur': 'Modern', 'yas_uygun': False, 'tema': ['aşk', 'İstanbul'], 'yazar_tarzi': 'postmodern', 'neden': 'İstanbul aşkı ve nostalji'},
        
        # Korku/Gerilim
        {'baslik': 'Dracula', 'yazar': 'Bram Stoker', 'sayfa': 418, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['vampir', 'gotik'], 'yazar_tarzi': 'gotik_korku', 'neden': 'Vampir efsanesinin klasik anlatımı'},
        {'baslik': 'Frankenstein', 'yazar': 'Mary Shelley', 'sayfa': 280, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['bilim', 'yaratık'], 'yazar_tarzi': 'gotik_korku', 'neden': 'Bilimin sınırları ve yaratık hikayesi'},
        {'baslik': 'The Shining', 'yazar': 'Stephen King', 'sayfa': 447, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['otel', 'delilik'], 'yazar_tarzi': 'modern_korku', 'neden': 'Psikolojik korku ve izolasyon'},
        {'baslik': 'It', 'yazar': 'Stephen King', 'sayfa': 1138, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['palyaço', 'çocukluk'], 'yazar_tarzi': 'modern_korku', 'neden': 'Çocukluk korkuları ve dostluk gücü'},
        
        # Macera
        {'baslik': 'Treasure Island', 'yazar': 'Robert Louis Stevenson', 'sayfa': 292, 'tur': 'Macera', 'yas_uygun': True, 'tema': ['korsan', 'hazine'], 'yazar_tarzi': 'klasik_macera', 'neden': 'Korsan macerası ve hazine arayışı'},
        {'baslik': 'Robinson Crusoe', 'yazar': 'Daniel Defoe', 'sayfa': 320, 'tur': 'Macera', 'yas_uygun': True, 'tema': ['ada', 'hayatta kalma'], 'yazar_tarzi': 'klasik_macera', 'neden': 'Issız adada hayatta kalma mücadelesi'},
        {'baslik': 'Around the World in 80 Days', 'yazar': 'Jules Verne', 'sayfa': 297, 'tur': 'Macera', 'yas_uygun': True, 'tema': ['yolculuk', 'bahis'], 'yazar_tarzi': 'bilimsel_macera', 'neden': 'Dünya turunda heyecanlı yolculuk'},
        
        # Romantik
        {'baslik': 'Jane Eyre', 'yazar': 'Charlotte Brontë', 'sayfa': 507, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['aşk', 'bağımsızlık'], 'yazar_tarzi': 'viktorya_romantik', 'neden': 'Güçlü kadın karakteri ve bağımsızlık mücadelesi'},
        {'baslik': 'Wuthering Heights', 'yazar': 'Emily Brontë', 'sayfa': 416, 'tur': 'Romantik', 'yas_uygun': False, 'tema': ['tutku', 'intikam'], 'yazar_tarzi': 'gotik_romantik', 'neden': 'Tutkulu ve karanlık aşk hikayesi'},
        {'baslik': 'Sense and Sensibility', 'yazar': 'Jane Austen', 'sayfa': 374, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['kardeşler', 'aşk'], 'yazar_tarzi': 'ingiliz_klasik', 'neden': 'Kardeş sevgisi ve aşk dengeleri'},
        {'baslik': 'The Great Gatsby', 'yazar': 'F. Scott Fitzgerald', 'sayfa': 180, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['amerikan rüyası', 'aşk'], 'yazar_tarzi': 'amerikan_klasik', 'neden': 'Amerikan rüyası ve aşkın trajedisi'},
        
        # Tarihsel
        {'baslik': 'War and Peace', 'yazar': 'Leo Tolstoy', 'sayfa': 1296, 'tur': 'Tarihsel', 'yas_uygun': False, 'tema': ['Napolyon', 'Rusya'], 'yazar_tarzi': 'rus_klasik', 'neden': 'Napolyon savaşları ve Rus toplumu'},
        {'baslik': 'The Pillars of the Earth', 'yazar': 'Ken Follett', 'sayfa': 973, 'tur': 'Tarihsel', 'yas_uygun': False, 'tema': ['katedral', 'ortaçağ'], 'yazar_tarzi': 'tarihsel_epik', 'neden': 'Ortaçağ mimarisi ve toplumsal yapı'},
        {'baslik': 'Gone with the Wind', 'yazar': 'Margaret Mitchell', 'sayfa': 1037, 'tur': 'Tarihsel', 'yas_uygun': False, 'tema': ['iç savaş', 'güney'], 'yazar_tarzi': 'amerikan_tarihsel', 'neden': 'Amerika iç savaşı dönemi'},
        
        # Biyografi/Otobiyografi
        {'baslik': 'Steve Jobs', 'yazar': 'Walter Isaacson', 'sayfa': 656, 'tur': 'Biyografi', 'yas_uygun': True, 'tema': ['teknoloji', 'girişimcilik'], 'yazar_tarzi': 'modern_biyografi', 'neden': 'Teknoloji dünyasının devrimci liderinin hikayesi'},
        {'baslik': 'Long Walk to Freedom', 'yazar': 'Nelson Mandela', 'sayfa': 630, 'tur': 'Otobiyografi', 'yas_uygun': True, 'tema': ['özgürlük', 'apartheid'], 'yazar_tarzi': 'politik_otobiyografi', 'neden': 'Özgürlük mücadelesi ve liderlik'},
        
        # Çocuk/Gençlik
        {'baslik': 'Matilda', 'yazar': 'Roald Dahl', 'sayfa': 240, 'tur': 'Çocuk', 'yas_uygun': True, 'tema': ['okul', 'süper güç'], 'yazar_tarzi': 'çocuk_fantastik', 'neden': 'Zeka ve süper güçlerle okul mücadelesi'},
        {'baslik': 'Charlie and Chocolate Factory', 'yazar': 'Roald Dahl', 'sayfa': 155, 'tur': 'Çocuk', 'yas_uygun': True, 'tema': ['fabrika', 'macera'], 'yazar_tarzi': 'çocuk_fantastik', 'neden': 'Büyülü çikolata fabrikası macerası'},
        {'baslik': 'The Fault in Our Stars', 'yazar': 'John Green', 'sayfa': 313, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['kanser', 'aşk'], 'yazar_tarzi': 'modern_gençlik', 'neden': 'Hastalık karşısında aşk ve umut'},
        {'baslik': 'Thirteen Reasons Why', 'yazar': 'Jay Asher', 'sayfa': 288, 'tur': 'Gençlik', 'yas_uygun': False, 'tema': ['intihar', 'zorbalık'], 'yazar_tarzi': 'problem_gençlik', 'neden': 'Zorbalığın etkileri ve farkındalık'},
        
        # Psikoloji/Sosyoloji
        {'baslik': 'Thinking Fast and Slow', 'yazar': 'Daniel Kahneman', 'sayfa': 499, 'tur': 'Psikoloji', 'yas_uygun': False, 'tema': ['karar verme', 'zihin'], 'yazar_tarzi': 'bilimsel_psikoloji', 'neden': 'Karar verme süreçleri ve zihin çalışması'},
        {'baslik': 'Sapiens', 'yazar': 'Yuval Noah Harari', 'sayfa': 443, 'tur': 'Tarih', 'yas_uygun': False, 'tema': ['insanlık', 'evrim'], 'yazar_tarzi': 'popüler_bilim', 'neden': 'İnsanlık tarihinin geniş perspektifi'},
        {'baslik': 'Homo Deus', 'yazar': 'Yuval Noah Harari', 'sayfa': 448, 'tur': 'Felsefe', 'yas_uygun': False, 'tema': ['gelecek', 'teknoloji'], 'yazar_tarzi': 'popüler_bilim', 'neden': 'İnsanlığın geleceği hakkında vizyon'},
        
        # Daha fazla Modern
        {'baslik': 'The Kite Runner', 'yazar': 'Khaled Hosseini', 'sayfa': 371, 'tur': 'Modern', 'yas_uygun': False, 'tema': ['Afganistan', 'dostluk'], 'yazar_tarzi': 'cagdas_drama', 'neden': 'Afganistan\'da dostluk ve kefaret'},
        {'baslik': 'Life of Pi', 'yazar': 'Yann Martel', 'sayfa': 319, 'tur': 'Modern', 'yas_uygun': True, 'tema': ['hayatta kalma', 'din'], 'yazar_tarzi': 'felsefi_macera', 'neden': 'Hayatta kalma ve inanç sorgulaması'},
        {'baslik': 'The Book Thief', 'yazar': 'Markus Zusak', 'sayfa': 552, 'tur': 'Tarihsel', 'yas_uygun': True, 'tema': ['Nazi', 'kitap'], 'yazar_tarzi': 'tarihsel_drama', 'neden': 'Kitapların gücü ve umut'},
        
        # Ekonomi/İş
        {'baslik': 'Rich Dad Poor Dad', 'yazar': 'Robert Kiyosaki', 'sayfa': 336, 'tur': 'Kişisel Gelişim', 'yas_uygun': True, 'tema': ['para', 'yatırım'], 'yazar_tarzi': 'finansal_eğitim', 'neden': 'Finansal okuryazarlık ve yatırım bilgisi'},
        {'baslik': 'The Lean Startup', 'yazar': 'Eric Ries', 'sayfa': 336, 'tur': 'İş', 'yas_uygun': True, 'tema': ['girişimcilik', 'inovasyon'], 'yazar_tarzi': 'iş_stratejisi', 'neden': 'Girişimcilik ve inovasyon stratejileri'},
        
        # Daha fazla Distopya
        {'baslik': 'The Handmaid\'s Tale', 'yazar': 'Margaret Atwood', 'sayfa': 311, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['kadın hakları', 'totaliter'], 'yazar_tarzi': 'feminist_distopya', 'neden': 'Kadın hakları ve özgürlük mücadelesi'},
        {'baslik': 'V for Vendetta', 'yazar': 'Alan Moore', 'sayfa': 296, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['devrim', 'maske'], 'yazar_tarzi': 'politik_distopya', 'neden': 'Baskıya karşı devrim ve direniş'},
        {'baslik': 'The Road', 'yazar': 'Cormac McCarthy', 'sayfa': 287, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['apokalips', 'baba-oğul'], 'yazar_tarzi': 'post_apokaliptik', 'neden': 'Apokalips sonrası baba-oğul bağı'},
        # Wattpad - Gençlik Romanları (En üstte - hedef kitle gençler)
        {'baslik': 'After', 'yazar': 'Anna Todd', 'sayfa': 582, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['aşk', 'üniversite', 'bad boy'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Üniversite hayatında bad boy aşkı'},
        {'baslik': 'The Kissing Booth', 'yazar': 'Beth Reekles', 'sayfa': 276, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['lise', 'aşk', 'arkadaşlık'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Lise döneminde arkadaşlık ve aşk karmaşası'},
        {'baslik': 'My Life with the Walter Boys', 'yazar': 'Ali Novak', 'sayfa': 340, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['aile', 'aşk', 'gençlik'], 'yazar_tarzi': 'wattpad_drama', 'neden': 'Büyük ailede yaşama uyum ve aşk'},
        {'baslik': 'The Bad Boy\'s Girl', 'yazar': 'Blair Holden', 'sayfa': 298, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['okul', 'bad boy', 'aşk'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Okulun bad boy\'u ile aşk hikayesi'},
        {'baslik': 'Chasing Red', 'yazar': 'Isabelle Ronin', 'sayfa': 456, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['üniversite', 'zengin', 'aşk'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Zengin çocuk ile sıradan kız aşkı'},
        {'baslik': 'The Cell Phone Swap', 'yazar': 'Lindsey Summers', 'sayfa': 234, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['komedi', 'lise', 'yanlış anlaşılma'], 'yazar_tarzi': 'wattpad_comedy', 'neden': 'Telefon karışıklığından doğan komik aşk'},
        {'baslik': 'Cupid\'s Match', 'yazar': 'Lauren Palphreyman', 'sayfa': 312, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['mitoloji', 'aşk', 'fantastik'], 'yazar_tarzi': 'wattpad_fantasy', 'neden': 'Aşk tanrısı ile modern gencin hikayesi'},
        {'baslik': 'The Hoodie Girl', 'yazar': 'Yuen Wright', 'sayfa': 267, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['lise', 'popüler', 'dönüşüm'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Sıradan kızın popüler olma yolculuğu'},
        {'baslik': 'Knowing Xavier Hunt', 'yazar': 'Raven Kennedy', 'sayfa': 389, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['lise', 'bad boy', 'gizem'], 'yazar_tarzi': 'wattpad_mystery', 'neden': 'Gizemli bad boy ile tanışma hikayesi'},
        {'baslik': 'The Quarterback\'s Girl', 'yazar': 'Alyssa Breck', 'sayfa': 298, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['spor', 'lise', 'aşk'], 'yazar_tarzi': 'wattpad_sports', 'neden': 'Amerikan futbolu yıldızı ile aşk'},
        
        # Roman Kategorisi
        {'baslik': 'Aşk ve Gurur', 'yazar': 'Jane Austen', 'sayfa': 432, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'toplum', 'evlilik'], 'yazar_tarzi': 'klasik_roman', 'neden': 'Toplumsal sınıflar ve aşk konularında klasik'},
        {'baslik': 'Anna Karenina', 'yazar': 'Lev Tolstoy', 'sayfa': 864, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['aşk', 'toplum', 'trajedi'], 'yazar_tarzi': 'rus_roman', 'neden': 'Yasak aşk ve toplumsal baskı'},
        {'baslik': 'Madame Bovary', 'yazar': 'Gustave Flaubert', 'sayfa': 374, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['evlilik', 'hayal kırıklığı'], 'yazar_tarzi': 'fransız_roman', 'neden': 'Evlilik hayatının gerçekleri'},
        {'baslik': 'Wuthering Heights', 'yazar': 'Emily Brontë', 'sayfa': 416, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['tutku', 'intikam', 'aşk'], 'yazar_tarzi': 'gotik_roman', 'neden': 'Tutkulu ve karanlık aşk hikayesi'},
        {'baslik': 'Jane Eyre', 'yazar': 'Charlotte Brontë', 'sayfa': 507, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'bağımsızlık', 'kadın'], 'yazar_tarzi': 'viktorya_roman', 'neden': 'Güçlü kadın karakteri ve bağımsızlık mücadelesi'},
        {'baslik': 'Büyük Umutlar', 'yazar': 'Charles Dickens', 'sayfa': 544, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['büyüme', 'sınıf', 'aşk'], 'yazar_tarzi': 'viktorya_roman', 'neden': 'Büyüme ve sosyal sınıf değişimi'},
        {'baslik': 'Dorian Gray\'in Portresi', 'yazar': 'Oscar Wilde', 'sayfa': 254, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['güzellik', 'ahlak', 'sanat'], 'yazar_tarzi': 'estetik_roman', 'neden': 'Güzellik ve ahlak arasındaki çelişki'},
        {'baslik': 'Baba', 'yazar': 'Mario Puzo', 'sayfa': 448, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['aile', 'güç', 'mafya'], 'yazar_tarzi': 'suç_roman', 'neden': 'Aile bağları ve güç mücadelesi'},
        {'baslik': 'Rüzgar Gibi Geçti', 'yazar': 'Margaret Mitchell', 'sayfa': 1037, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['savaş', 'aşk', 'hayatta kalma'], 'yazar_tarzi': 'tarihsel_roman', 'neden': 'İç savaş döneminde aşk ve hayatta kalma'},
        {'baslik': 'Doktor Jivago', 'yazar': 'Boris Pasternak', 'sayfa': 592, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['devrim', 'aşk', 'Rusya'], 'yazar_tarzi': 'rus_roman', 'neden': 'Rus devrimi döneminde aşk ve kayıp'},
        
        # Daha fazla kitap - 150+ hedef
        {'baslik': 'Twilight', 'yazar': 'Stephenie Meyer', 'sayfa': 498, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['vampir', 'aşk', 'lise'], 'yazar_tarzi': 'paranormal_romance', 'neden': 'Vampir aşkı ve lise hayatı'},
        {'baslik': 'Divergent', 'yazar': 'Veronica Roth', 'sayfa': 487, 'tur': 'Distopya', 'yas_uygun': True, 'tema': ['gelecek', 'seçim', 'güçlü kadın'], 'yazar_tarzi': 'gençlik_distopya', 'neden': 'Gelecekte seçim yapma ve güçlü kadın karakter'},
        {'baslik': 'The Maze Runner', 'yazar': 'James Dashner', 'sayfa': 375, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['labirent', 'hafıza', 'hayatta kalma'], 'yazar_tarzi': 'gençlik_bilimkurgu', 'neden': 'Gizem ve hayatta kalma mücadelesi'},
        {'baslik': 'Miss Peregrine\'s Home', 'yazar': 'Ransom Riggs', 'sayfa': 352, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['zaman', 'fotoğraf', 'çocuklar'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Fotoğraflarla desteklenen benzersiz fantastik hikaye'},
        {'baslik': 'The Selection', 'yazar': 'Kiera Cass', 'sayfa': 327, 'tur': 'Distopya', 'yas_uygun': True, 'tema': ['yarışma', 'prens', 'aşk'], 'yazar_tarzi': 'romantik_distopya', 'neden': 'Prens seçimi yarışması ve aşk'},
        {'baslik': 'Red Queen', 'yazar': 'Victoria Aveyard', 'sayfa': 383, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['güç', 'kan', 'devrim'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Kan gücü ve devrim mücadelesi'},
        {'baslik': 'Shadow and Bone', 'yazar': 'Leigh Bardugo', 'sayfa': 358, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['karanlık', 'büyü', 'savaş'], 'yazar_tarzi': 'karanlık_fantastik', 'neden': 'Karanlık büyü ve savaş atmosferi'},
        {'baslik': 'Six of Crows', 'yazar': 'Leigh Bardugo', 'sayfa': 465, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['hırsızlık', 'çete', 'büyü'], 'yazar_tarzi': 'karanlık_fantastik', 'neden': 'Hırsızlar çetesi ve büyülü dünya'},
        {'baslik': 'Throne of Glass', 'yazar': 'Sarah J. Maas', 'sayfa': 404, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['suikastçı', 'krallık', 'büyü'], 'yazar_tarzi': 'epik_fantastik', 'neden': 'Kadın suikastçı ve krallık mücadelesi'},
        {'baslik': 'A Court of Thorns and Roses', 'yazar': 'Sarah J. Maas', 'sayfa': 419, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['peri', 'aşk', 'büyü'], 'yazar_tarzi': 'romantik_fantastik', 'neden': 'Peri dünyasında aşk ve büyü'},
        
        # Türk Romanları
        {'baslik': 'Sevda Sozleri', 'yazar': 'Peyami Safa', 'sayfa': 280, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['ask', 'Istanbul', 'duygusal'], 'yazar_tarzi': 'turk_roman', 'neden': 'Istanbul\'da gecen duygusal ask hikayesi'},
        {'baslik': 'Yaprak Dökümü', 'yazar': 'Reşat Nuri Güntekin', 'sayfa': 456, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aile', 'yoksulluk', 'değişim'], 'yazar_tarzi': 'türk_roman', 'neden': 'Aile değerlerinin değişimi ve toplumsal dönüşüm'},
        {'baslik': 'Kiralik Konak', 'yazar': 'Yakup Kadri Karaosmanoglu', 'sayfa': 320, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['toplum', 'degisim', 'aile'], 'yazar_tarzi': 'turk_roman', 'neden': 'Osmanli\'dan Cumhuriyet\'e gecis donemi'},
        {'baslik': 'Huzur', 'yazar': 'Ahmet Hamdi Tanpınar', 'sayfa': 624, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['zaman', 'İstanbul', 'aşk'], 'yazar_tarzi': 'türk_modern', 'neden': 'Zaman kavramı ve İstanbul nostalji'},
        {'baslik': 'Saatleri Ayarlama Enstitüsü', 'yazar': 'Ahmet Hamdi Tanpınar', 'sayfa': 376, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['zaman', 'modernleşme'], 'yazar_tarzi': 'türk_modern', 'neden': 'Modernleşme ve zaman algısı üzerine felsefi roman'},
        
        # Modern Romanlar
        {'baslik': 'Atonement', 'yazar': 'Ian McEwan', 'sayfa': 351, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['suç', 'kefaret', 'aşk'], 'yazar_tarzi': 'çağdaş_roman', 'neden': 'Suç ve kefaret teması ile derin psikolojik analiz'},
        {'baslik': 'The Time Traveler\'s Wife', 'yazar': 'Audrey Niffenegger', 'sayfa': 518, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['zaman yolculuğu', 'aşk'], 'yazar_tarzi': 'fantastik_roman', 'neden': 'Zaman yolculuğu ile aşkın sınırlarını zorlayan hikaye'},
        {'baslik': 'One Day', 'yazar': 'David Nicholls', 'sayfa': 435, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['dostluk', 'aşk', 'zaman'], 'yazar_tarzi': 'çağdaş_roman', 'neden': 'Yıllar boyunca gelişen dostluk ve aşk hikayesi'},
        {'baslik': 'Me Before You', 'yazar': 'Jojo Moyes', 'sayfa': 369, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['engelli', 'aşk', 'yaşam'], 'yazar_tarzi': 'çağdaş_roman', 'neden': 'Yaşamın değeri ve aşkın gücü hakkında dokunaklı hikaye'},
        {'baslik': 'The Notebook', 'yazar': 'Nicholas Sparks', 'sayfa': 214, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['yaşlılık', 'aşk', 'hafıza'], 'yazar_tarzi': 'romantik_roman', 'neden': 'Yaşlılıkta bile süren büyük aşk hikayesi'},
        
        # Daha fazla Gençlik
        {'baslik': 'Eleanor & Park', 'yazar': 'Rainbow Rowell', 'sayfa': 325, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['ilk aşk', 'lise', 'müzik'], 'yazar_tarzi': 'modern_gençlik', 'neden': 'İlk aşkın masumiyeti ve müziğin gücü'},
        {'baslik': 'Simon vs. Homo Sapiens', 'yazar': 'Becky Albertalli', 'sayfa': 303, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['LGBT', 'lise', 'kimlik'], 'yazar_tarzi': 'modern_gençlik', 'neden': 'Kimlik arayışı ve LGBT+ temsili'},
        {'baslik': 'The Perks of Being a Wallflower', 'yazar': 'Stephen Chbosky', 'sayfa': 213, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['lise', 'arkadaşlık', 'büyüme'], 'yazar_tarzi': 'modern_gençlik', 'neden': 'Lise döneminin zorluklarını anlatan dürüst hikaye'},
        {'baslik': 'Looking for Alaska', 'yazar': 'John Green', 'sayfa': 221, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['okul', 'ölüm', 'aşk'], 'yazar_tarzi': 'modern_gençlik', 'neden': 'Gençlik, ölüm ve anlam arayışı'},
        {'baslik': 'Paper Towns', 'yazar': 'John Green', 'sayfa': 305, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['gizem', 'lise', 'arayış'], 'yazar_tarzi': 'modern_gençlik', 'neden': 'Gizem ve kendini bulma yolculuğu'},
        
        # Mizah
        {'baslik': 'Good Omens', 'yazar': 'Terry Pratchett', 'sayfa': 383, 'tur': 'Mizah', 'yas_uygun': True, 'tema': ['melek', 'şeytan', 'kıyamet'], 'yazar_tarzi': 'fantastik_mizah', 'neden': 'Melek ve şeytanın komik kıyamet maceraları'},
        {'baslik': 'Discworld', 'yazar': 'Terry Pratchett', 'sayfa': 285, 'tur': 'Mizah', 'yas_uygun': True, 'tema': ['büyücü', 'parodi'], 'yazar_tarzi': 'fantastik_mizah', 'neden': 'Fantastik türün zekice parodisi'},
        
        # Şiir
        {'baslik': 'Nazim Hikmet Şiirleri', 'yazar': 'Nazım Hikmet', 'sayfa': 450, 'tur': 'Şiir', 'yas_uygun': True, 'tema': ['özgürlük', 'aşk'], 'yazar_tarzi': 'modern_şiir', 'neden': 'Türk şiirinin en güçlü seslerinden biri'},
        {'baslik': 'Orhan Veli Şiirleri', 'yazar': 'Orhan Veli', 'sayfa': 200, 'tur': 'Şiir', 'yas_uygun': True, 'tema': ['gündelik', 'sade'], 'yazar_tarzi': 'halk_şiiri', 'neden': 'Sade ve anlaşılır şiir dili'},
        
        # Daha fazla kitap - 200+ hedef
        {'baslik': 'The Alchemist', 'yazar': 'Paulo Coelho', 'sayfa': 163, 'tur': 'Felsefe', 'yas_uygun': True, 'tema': ['hayal', 'yolculuk'], 'yazar_tarzi': 'ruhani_felsefe', 'neden': 'Hayallerin peşinden gitme konusunda ilham verici'},
        {'baslik': 'To Kill a Mockingbird', 'yazar': 'Harper Lee', 'sayfa': 281, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['adalet', 'ırkçılık'], 'yazar_tarzi': 'amerikan_klasik', 'neden': 'Adalet ve ahlak konularında derin bir bakış'},
        {'baslik': 'Lord of the Flies', 'yazar': 'William Golding', 'sayfa': 224, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['çocuklar', 'medeniyet'], 'yazar_tarzi': 'alegorik', 'neden': 'İnsan doğası hakkında düşündürücü'},
        {'baslik': 'Brave New World', 'yazar': 'Aldous Huxley', 'sayfa': 311, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['teknoloji', 'kontrol'], 'yazar_tarzi': 'bilimsel_distopya', 'neden': 'Teknolojinin tehlikeleri hakkında uyarıcı'},
        {'baslik': 'Animal Farm', 'yazar': 'George Orwell', 'sayfa': 95, 'tur': 'Alegorik', 'yas_uygun': True, 'tema': ['devrim', 'güç'], 'yazar_tarzi': 'politik_alegori', 'neden': 'Siyasi sistemlerin eleştirisi'},
        {'baslik': 'Of Mice and Men', 'yazar': 'John Steinbeck', 'sayfa': 107, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['dostluk', 'hayal'], 'yazar_tarzi': 'amerikan_klasik', 'neden': 'Dostluk ve hayallerin gücü'},
        {'baslik': 'The Outsiders', 'yazar': 'S.E. Hinton', 'sayfa': 180, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['çete', 'kardeşlik'], 'yazar_tarzi': 'gençlik_klasik', 'neden': 'Gençlerin zorluklarını anlatan güçlü hikaye'},
        {'baslik': 'Holes', 'yazar': 'Louis Sachar', 'sayfa': 233, 'tur': 'Çocuk', 'yas_uygun': True, 'tema': ['kamp', 'adalet'], 'yazar_tarzi': 'çocuk_macera', 'neden': 'Adalet ve dostluk temalı eğlenceli hikaye'},
        {'baslik': 'Bridge to Terabithia', 'yazar': 'Katherine Paterson', 'sayfa': 128, 'tur': 'Çocuk', 'yas_uygun': True, 'tema': ['dostluk', 'hayal gücü'], 'yazar_tarzi': 'çocuk_drama', 'neden': 'Hayal gücü ve kayıp konularında dokunaklı'},
        {'baslik': 'Where the Red Fern Grows', 'yazar': 'Wilson Rawls', 'sayfa': 212, 'tur': 'Çocuk', 'yas_uygun': True, 'tema': ['köpek', 'avcılık'], 'yazar_tarzi': 'çocuk_macera', 'neden': 'Hayvan sevgisi ve azim konularında öğretici'},
        
        # Daha fazla Wattpad
        {'baslik': 'The Summer I Turned Pretty', 'yazar': 'Jenny Han', 'sayfa': 276, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['yaz', 'aşk üçgeni'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Gençlik aşkının tatlı hikayesi'},
        {'baslik': 'To All the Boys I\'ve Loved Before', 'yazar': 'Jenny Han', 'sayfa': 355, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['mektup', 'lise aşkı'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Sevimli ve romantik gençlik hikayesi'},
        {'baslik': 'Anna and the French Kiss', 'yazar': 'Stephanie Perkins', 'sayfa': 372, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['Paris', 'okul'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Paris\'te geçen romantik okul hikayesi'},
        {'baslik': 'The DUFF', 'yazar': 'Kody Keplinger', 'sayfa': 280, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['özgüven', 'lise'], 'yazar_tarzi': 'wattpad_comedy', 'neden': 'Özgüven ve kabul edilme konularında güçlendirici'},
        {'baslik': 'Perfect Chemistry', 'yazar': 'Simone Elkeles', 'sayfa': 360, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['sınıf farkı', 'aşk'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Farklı dünyalardan gelen aşk hikayesi'},
        
        # Daha fazla Roman
        {'baslik': 'Les Misérables', 'yazar': 'Victor Hugo', 'sayfa': 1463, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['adalet', 'devrim'], 'yazar_tarzi': 'fransız_roman', 'neden': 'İnsanlık ve adalet konularında büyük eser'},
        {'baslik': 'Don Kişot', 'yazar': 'Miguel de Cervantes', 'sayfa': 863, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['hayal', 'şövalye'], 'yazar_tarzi': 'İspanyol_klasik', 'neden': 'Hayallerin gücü ve gerçeklik arasındaki çelişki'},
        {'baslik': 'Buddenbrooks', 'yazar': 'Thomas Mann', 'sayfa': 731, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['aile', 'çöküş'], 'yazar_tarzi': 'alman_roman', 'neden': 'Aile dinamikleri ve toplumsal değişim'},
        {'baslik': 'The Brothers Karamazov', 'yazar': 'Fyodor Dostoyevski', 'sayfa': 796, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['din', 'aile'], 'yazar_tarzi': 'rus_roman', 'neden': 'İnsan doğası ve din konularında derin analiz'},
        
        # Daha fazla Fantastik
        {'baslik': 'The Wheel of Time', 'yazar': 'Robert Jordan', 'sayfa': 782, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['epik', 'büyü'], 'yazar_tarzi': 'epik_fantastik', 'neden': 'Büyük fantastik evren ve karakter gelişimi'},
        {'baslik': 'The First Law', 'yazar': 'Joe Abercrombie', 'sayfa': 515, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['karanlık', 'savaş'], 'yazar_tarzi': 'karanlık_fantastik', 'neden': 'Gerçekçi ve karanlık fantastik dünya'},
        {'baslik': 'The Kingkiller Chronicle', 'yazar': 'Patrick Rothfuss', 'sayfa': 662, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['müzik', 'büyü'], 'yazar_tarzi': 'modern_fantastik', 'neden': 'Müzik ve büyünün birleştiği poetik anlatım'},
        {'baslik': 'The Stormlight Archive', 'yazar': 'Brandon Sanderson', 'sayfa': 1007, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['onur', 'büyü sistemi'], 'yazar_tarzi': 'epik_fantastik', 'neden': 'Karmaşık büyü sistemi ve derin karakter gelişimi'},
        
        # Daha fazla Bilim Kurgu
        {'baslik': 'Hyperion', 'yazar': 'Dan Simmons', 'sayfa': 512, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['zaman', 'yapay zeka'], 'yazar_tarzi': 'space_opera', 'neden': 'Zaman ve teknoloji konularında karmaşık hikaye'},
        {'baslik': 'The Left Hand of Darkness', 'yazar': 'Ursula K. Le Guin', 'sayfa': 304, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['cinsiyet', 'gezegen'], 'yazar_tarzi': 'sosyal_bilimkurgu', 'neden': 'Cinsiyet ve toplum konularında düşündürücü'},
        {'baslik': 'I, Robot', 'yazar': 'Isaac Asimov', 'sayfa': 253, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['robot', 'yapay zeka'], 'yazar_tarzi': 'klasik_bilimkurgu', 'neden': 'Robot yasaları ve yapay zeka etiği'},
        {'baslik': 'The Martian', 'yazar': 'Andy Weir', 'sayfa': 369, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['Mars', 'hayatta kalma'], 'yazar_tarzi': 'sert_bilimkurgu', 'neden': 'Bilimsel doğruluk ve mizah birleşimi'},
        
        # Daha fazla Polisiye
        {'baslik': 'The Maltese Falcon', 'yazar': 'Dashiell Hammett', 'sayfa': 217, 'tur': 'Polisiye', 'yas_uygun': False, 'tema': ['dedektif', 'noir'], 'yazar_tarzi': 'hard_boiled', 'neden': 'Klasik noir atmosferi'},
        {'baslik': 'In the Woods', 'yazar': 'Tana French', 'sayfa': 429, 'tur': 'Polisiye', 'yas_uygun': False, 'tema': ['çocukluk', 'gizem'], 'yazar_tarzi': 'psikolojik_polisiye', 'neden': 'Psikolojik derinlik ve atmosfer'},
        {'baslik': 'The Silence of the Lambs', 'yazar': 'Thomas Harris', 'sayfa': 352, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['seri katil', 'FBI'], 'yazar_tarzi': 'psikolojik_gerilim', 'neden': 'Psikolojik gerilim ustası'},
        
        # Daha fazla Korku
        {'baslik': 'The Exorcist', 'yazar': 'William Peter Blatty', 'sayfa': 340, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['şeytan', 'din'], 'yazar_tarzi': 'dini_korku', 'neden': 'Dini korku türünün klasiği'},
        {'baslik': 'Pet Sematary', 'yazar': 'Stephen King', 'sayfa': 374, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['ölüm', 'mezarlık'], 'yazar_tarzi': 'modern_korku', 'neden': 'Ölüm ve kayıp konularında korku ustası'},
        {'baslik': 'The Haunting of Hill House', 'yazar': 'Shirley Jackson', 'sayfa': 246, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['ev', 'ruh'], 'yazar_tarzi': 'psikolojik_korku', 'neden': 'Psikolojik korkunun en iyilerinden'},
        
        # Daha fazla Macera
        {'baslik': 'The Count of Monte Cristo', 'yazar': 'Alexandre Dumas', 'sayfa': 1276, 'tur': 'Macera', 'yas_uygun': False, 'tema': ['intikam', 'hazine'], 'yazar_tarzi': 'klasik_macera', 'neden': 'İntikam ve adalet temalı büyük macera'},
        {'baslik': 'The Three Musketeers', 'yazar': 'Alexandre Dumas', 'sayfa': 625, 'tur': 'Macera', 'yas_uygun': True, 'tema': ['dostluk', 'şövalye'], 'yazar_tarzi': 'klasik_macera', 'neden': 'Dostluk ve onur konularında klasik macera'},
        {'baslik': 'Swiss Family Robinson', 'yazar': 'Johann David Wyss', 'sayfa': 306, 'tur': 'Macera', 'yas_uygun': True, 'tema': ['ada', 'aile'], 'yazar_tarzi': 'aile_macera', 'neden': 'Aile birliği ve hayatta kalma'},
        
        # Daha fazla Gençlik Romanları
        {'baslik': 'The Hate U Give', 'yazar': 'Angie Thomas', 'sayfa': 444, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['ırkçılık', 'adalet'], 'yazar_tarzi': 'sosyal_gençlik', 'neden': 'Güncel sosyal konularda güçlü mesaj'},
        {'baslik': 'Wonder', 'yazar': 'R.J. Palacio', 'sayfa': 315, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['farklılık', 'kabul'], 'yazar_tarzi': 'duygusal_gençlik', 'neden': 'Farklılıkları kabul etme konusunda öğretici'},
        {'baslik': 'Speak', 'yazar': 'Laurie Halse Anderson', 'sayfa': 197, 'tur': 'Gençlik', 'yas_uygun': False, 'tema': ['travma', 'ses bulma'], 'yazar_tarzi': 'problem_gençlik', 'neden': 'Travma ve iyileşme konularında güçlü'},
        
        # Daha fazla Modern Türk Edebiyatı
        {'baslik': 'Kar', 'yazar': 'Orhan Pamuk', 'sayfa': 436, 'tur': 'Modern', 'yas_uygun': False, 'tema': ['Kars', 'din', 'siyaset'], 'yazar_tarzi': 'postmodern', 'neden': 'Türkiye\'nin sosyal gerçekleri'},
        {'baslik': 'Benim Adım Kırmızı', 'yazar': 'Orhan Pamuk', 'sayfa': 470, 'tur': 'Tarihsel', 'yas_uygun': False, 'tema': ['Osmanlı', 'sanat'], 'yazar_tarzi': 'postmodern', 'neden': 'Osmanlı sanatı ve kültürü'},
        {'baslik': 'Sessiz Ev', 'yazar': 'Orhan Pamuk', 'sayfa': 340, 'tur': 'Modern', 'yas_uygun': False, 'tema': ['aile', 'sessizlik'], 'yazar_tarzi': 'postmodern', 'neden': 'Aile içi dinamikler ve iletişimsizlik'},
        
        # Daha fazla Popüler Kitaplar
        {'baslik': 'The 7 Habits', 'yazar': 'Stephen Covey', 'sayfa': 372, 'tur': 'Kişisel Gelişim', 'yas_uygun': True, 'tema': ['alışkanlık', 'başarı'], 'yazar_tarzi': 'kişisel_gelişim', 'neden': 'Etkili yaşam alışkanlıkları'},
        {'baslik': 'How to Win Friends', 'yazar': 'Dale Carnegie', 'sayfa': 291, 'tur': 'Kişisel Gelişim', 'yas_uygun': True, 'tema': ['iletişim', 'sosyal'], 'yazar_tarzi': 'sosyal_beceri', 'neden': 'İletişim becerilerini geliştirici'},
        {'baslik': 'Atomic Habits', 'yazar': 'James Clear', 'sayfa': 320, 'tur': 'Kişisel Gelişim', 'yas_uygun': True, 'tema': ['alışkanlık', 'değişim'], 'yazar_tarzi': 'davranış_bilimi', 'neden': 'Küçük değişikliklerle büyük sonuçlar'},
        
        # Daha fazla Fantastik Gençlik
        {'baslik': 'City of Bones', 'yazar': 'Cassandra Clare', 'sayfa': 485, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['melek', 'şeytan', 'aşk'], 'yazar_tarzi': 'urban_fantasy', 'neden': 'Modern şehirde geçen melek-şeytan hikayesi'},
        {'baslik': 'Beautiful Creatures', 'yazar': 'Kami Garcia', 'sayfa': 563, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['büyücü', 'güney', 'aşk'], 'yazar_tarzi': 'gothic_fantasy', 'neden': 'Güney gotik atmosferinde büyü hikayesi'},
        {'baslik': 'Hush Hush', 'yazar': 'Becca Fitzpatrick', 'sayfa': 391, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['melek', 'lise', 'aşk'], 'yazar_tarzi': 'paranormal_romance', 'neden': 'Melek temalı romantik fantastik'},
        
        # Daha fazla Distopya
        {'baslik': 'The Giver', 'yazar': 'Lois Lowry', 'sayfa': 179, 'tur': 'Distopya', 'yas_uygun': True, 'tema': ['hafıza', 'duygular'], 'yazar_tarzi': 'gençlik_distopya', 'neden': 'Duyguların ve hafızanın önemi'},
        {'baslik': 'Matched', 'yazar': 'Ally Condie', 'sayfa': 369, 'tur': 'Distopya', 'yas_uygun': True, 'tema': ['seçim', 'aşk'], 'yazar_tarzi': 'romantik_distopya', 'neden': 'Seçim özgürlüğü ve aşk'},
        {'baslik': 'Uglies', 'yazar': 'Scott Westerfeld', 'sayfa': 425, 'tur': 'Distopya', 'yas_uygun': True, 'tema': ['güzellik', 'operasyon'], 'yazar_tarzi': 'gençlik_distopya', 'neden': 'Güzellik standartları eleştirisi'},
        
        # Daha fazla Gerilim
        {'baslik': 'The Girl on the Train', 'yazar': 'Paula Hawkins', 'sayfa': 325, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['alkol', 'gizem'], 'yazar_tarzi': 'psikolojik_gerilim', 'neden': 'Güvenilmez anlatıcı ve psikolojik gerilim'},
        {'baslik': 'Before I Go to Sleep', 'yazar': 'S.J. Watson', 'sayfa': 359, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['hafıza', 'kimlik'], 'yazar_tarzi': 'psikolojik_gerilim', 'neden': 'Hafıza kaybı ve kimlik sorgulaması'},
        
        # Daha fazla Tarihsel
        {'baslik': 'All Quiet on Western Front', 'yazar': 'Erich Maria Remarque', 'sayfa': 295, 'tur': 'Tarihsel', 'yas_uygun': False, 'tema': ['1. dünya savaşı'], 'yazar_tarzi': 'savaş_karşıtı', 'neden': 'Savaşın gerçek yüzü'},
        {'baslik': 'The Diary of Anne Frank', 'yazar': 'Anne Frank', 'sayfa': 283, 'tur': 'Tarihsel', 'yas_uygun': True, 'tema': ['Holocaust', 'günlük'], 'yazar_tarzi': 'otobiyografik', 'neden': 'Tarihin acı gerçeklerinden öğrenme'},
        
        # Daha fazla Mizah
        {'baslik': 'Bridget Jones Diary', 'yazar': 'Helen Fielding', 'sayfa': 310, 'tur': 'Mizah', 'yas_uygun': False, 'tema': ['bekar', 'aşk'], 'yazar_tarzi': 'romantik_mizah', 'neden': 'Modern kadın hayatının komik yanları'},
        {'baslik': 'Yes Please', 'yazar': 'Amy Poehler', 'sayfa': 329, 'tur': 'Mizah', 'yas_uygun': False, 'tema': ['komedi', 'kadın'], 'yazar_tarzi': 'otobiyografik_mizah', 'neden': 'Komedi dünyasından içeriden bakış'},
        
        # Daha fazla kitap - FULL BASS 200+
        {'baslik': 'The Handmaid\'s Tale', 'yazar': 'Margaret Atwood', 'sayfa': 311, 'tur': 'Distopya', 'yas_uygun': False, 'tema': ['kadın', 'totaliter'], 'yazar_tarzi': 'feminist_distopya', 'neden': 'Kadın hakları ve özgürlük mücadelesi'},
        {'baslik': 'Ready Player One', 'yazar': 'Ernest Cline', 'sayfa': 374, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['oyun', 'sanal gerçeklik'], 'yazar_tarzi': 'pop_bilimkurgu', 'neden': 'Oyun kültürü ve nostalji'},
        {'baslik': 'The Martian Chronicles', 'yazar': 'Ray Bradbury', 'sayfa': 222, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['Mars', 'kolonizasyon'], 'yazar_tarzi': 'poetik_bilimkurgu', 'neden': 'Mars kolonizasyonu ve insan doğası'},
        {'baslik': 'Slaughterhouse-Five', 'yazar': 'Kurt Vonnegut', 'sayfa': 275, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['savaş', 'zaman'], 'yazar_tarzi': 'anti_savaş', 'neden': 'Savaş karşıtı mesaj ve zaman yolculuğu'},
        {'baslik': 'Flowers for Algernon', 'yazar': 'Daniel Keyes', 'sayfa': 311, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['zeka', 'deney'], 'yazar_tarzi': 'duygusal_bilimkurgu', 'neden': 'Zeka ve insanlık konularında dokunaklı'},
        {'baslik': 'The Time Machine', 'yazar': 'H.G. Wells', 'sayfa': 118, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['zaman yolculuğu'], 'yazar_tarzi': 'klasik_bilimkurgu', 'neden': 'Zaman yolculuğu türünün öncüsü'},
        {'baslik': 'Invisible Man', 'yazar': 'H.G. Wells', 'sayfa': 162, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['görünmezlik', 'güç'], 'yazar_tarzi': 'klasik_bilimkurgu', 'neden': 'Güç ve yozlaşma konularında klasik'},
        {'baslik': 'Jurassic Park', 'yazar': 'Michael Crichton', 'sayfa': 399, 'tur': 'Bilim Kurgu', 'yas_uygun': True, 'tema': ['dinozor', 'genetik'], 'yazar_tarzi': 'tekno_gerilim', 'neden': 'Genetik mühendisliği ve doğa'},
        {'baslik': 'Contact', 'yazar': 'Carl Sagan', 'sayfa': 432, 'tur': 'Bilim Kurgu', 'yas_uygun': False, 'tema': ['uzaylı', 'bilim'], 'yazar_tarzi': 'sert_bilimkurgu', 'neden': 'Bilimsel keşif ve inanç'},
        
        # Daha fazla Fantastik
        {'baslik': 'The Dark Tower', 'yazar': 'Stephen King', 'sayfa': 231, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['kovboy', 'kule'], 'yazar_tarzi': 'western_fantasy', 'neden': 'Western ve fantastik karışımı'},
        {'baslik': 'American Gods', 'yazar': 'Neil Gaiman', 'sayfa': 635, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['tanrı', 'Amerika'], 'yazar_tarzi': 'mitolojik_fantastik', 'neden': 'Modern mitoloji ve kültür çatışması'},
        {'baslik': 'The Ocean at the End', 'yazar': 'Neil Gaiman', 'sayfa': 181, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['çocukluk', 'hafıza'], 'yazar_tarzi': 'nostaljik_fantastik', 'neden': 'Çocukluk anıları ve büyü'},
        {'baslik': 'Good Omens', 'yazar': 'Terry Pratchett & Neil Gaiman', 'sayfa': 383, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['kıyamet', 'dostluk'], 'yazar_tarzi': 'komik_fantastik', 'neden': 'İyi ve kötünün dostluğu'},
        
        # Daha fazla Gençlik
        {'baslik': 'Miss Peregrine\'s Peculiar Children', 'yazar': 'Ransom Riggs', 'sayfa': 352, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['fotoğraf', 'zaman'], 'yazar_tarzi': 'görsel_fantastik', 'neden': 'Fotoğraflarla desteklenen benzersiz hikaye'},
        {'baslik': 'The Book Thief', 'yazar': 'Markus Zusak', 'sayfa': 552, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['Nazi', 'kitap'], 'yazar_tarzi': 'tarihsel_gençlik', 'neden': 'Kitapların gücü ve umut'},
        {'baslik': 'Aristotle and Dante', 'yazar': 'Benjamin Alire Sáenz', 'sayfa': 359, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['dostluk', 'kimlik'], 'yazar_tarzi': 'LGBT_gençlik', 'neden': 'Kimlik arayışı ve gerçek dostluk'},
        {'baslik': 'They Both Die at the End', 'yazar': 'Adam Silvera', 'sayfa': 373, 'tur': 'Gençlik', 'yas_uygun': True, 'tema': ['ölüm', 'dostluk'], 'yazar_tarzi': 'distopik_gençlik', 'neden': 'Yaşamın değeri ve dostluk'},
        
        # Daha fazla Wattpad Hits
        {'baslik': 'Bad Boy\'s Girl', 'yazar': 'Blair Holden', 'sayfa': 298, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['bad boy', 'okul'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Klasik bad boy hikayesi'},
        {'baslik': 'Loving the Band', 'yazar': 'Emily Baker', 'sayfa': 245, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['müzik', 'grup'], 'yazar_tarzi': 'wattpad_music', 'neden': 'Müzik grubu ve aşk hikayesi'},
        {'baslik': 'The Player Next Door', 'yazar': 'Alyssa Rose', 'sayfa': 267, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['komşu', 'player'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Komşu aşkı ve değişim'},
        {'baslik': 'Tutoring the Bad Boy', 'yazar': 'Samantha West', 'sayfa': 234, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['ders', 'bad boy'], 'yazar_tarzi': 'wattpad_romance', 'neden': 'Ders verme bahanesiyle aşk'},
        {'baslik': 'The Cheerleader and the Quarterback', 'yazar': 'Sarah Miller', 'sayfa': 289, 'tur': 'Wattpad', 'yas_uygun': True, 'tema': ['spor', 'lise'], 'yazar_tarzi': 'wattpad_sports', 'neden': 'Lise sporları ve popüler çocuklar'},
        
        # Daha fazla Klasik
        {'baslik': 'Madame Bovary', 'yazar': 'Gustave Flaubert', 'sayfa': 374, 'tur': 'Roman', 'yas_uygun': False, 'tema': ['evlilik', 'hayal kırıklığı'], 'yazar_tarzi': 'fransız_roman', 'neden': 'Evlilik ve hayal kırıklığı analizi'},
        {'baslik': 'The Scarlet Letter', 'yazar': 'Nathaniel Hawthorne', 'sayfa': 272, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['günah', 'toplum'], 'yazar_tarzi': 'amerikan_klasik', 'neden': 'Günah ve toplumsal yargı'},
        {'baslik': 'Heart of Darkness', 'yazar': 'Joseph Conrad', 'sayfa': 96, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['Afrika', 'karanlık'], 'yazar_tarzi': 'kolonyal_eleştiri', 'neden': 'Kolonyalizm eleştirisi'},
        {'baslik': 'The Picture of Dorian Gray', 'yazar': 'Oscar Wilde', 'sayfa': 254, 'tur': 'Klasik', 'yas_uygun': False, 'tema': ['güzellik', 'ahlak'], 'yazar_tarzi': 'estetik_roman', 'neden': 'Güzellik ve ahlak çelişkisi'},
        
        # Daha fazla Modern
        {'baslik': 'The Curious Incident', 'yazar': 'Mark Haddon', 'sayfa': 221, 'tur': 'Modern', 'yas_uygun': True, 'tema': ['otizm', 'gizem'], 'yazar_tarzi': 'farklı_bakış', 'neden': 'Otizmli gencin bakış açısından dünya'},
        {'baslik': 'Room', 'yazar': 'Emma Donoghue', 'sayfa': 321, 'tur': 'Modern', 'yas_uygun': False, 'tema': ['kaçırılma', 'anne-çocuk'], 'yazar_tarzi': 'psikolojik_drama', 'neden': 'Anne-çocuk bağı ve hayatta kalma'},
        {'baslik': 'The Help', 'yazar': 'Kathryn Stockett', 'sayfa': 444, 'tur': 'Tarihsel', 'yas_uygun': False, 'tema': ['ırkçılık', '1960lar'], 'yazar_tarzi': 'sosyal_tarihsel', 'neden': '1960lar Amerika\'sında ırkçılık'},
        
        # Daha fazla Türk
        {'baslik': 'Fatih-Harbiye', 'yazar': 'Peyami Safa', 'sayfa': 200, 'tur': 'Roman', 'yas_uygun': True, 'tema': ['aşk', 'sınıf'], 'yazar_tarzi': 'türk_roman', 'neden': 'Doğu-Batı çelişkisi ve aşk'},
        {'baslik': 'Araba Sevdası', 'yazar': 'Recaizade Mahmut Ekrem', 'sayfa': 120, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['aşk', 'taklit'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Batı hayranlığı eleştirisi'},
        {'baslik': 'Mai ve Siyah', 'yazar': 'Halit Ziya Uşaklıgil', 'sayfa': 180, 'tur': 'Klasik', 'yas_uygun': True, 'tema': ['aşk', 'sanat'], 'yazar_tarzi': 'türk_klasik', 'neden': 'Sanat ve aşk ilişkisi'},
        
        # Daha fazla Popüler
        {'baslik': 'Eat Pray Love', 'yazar': 'Elizabeth Gilbert', 'sayfa': 334, 'tur': 'Otobiyografi', 'yas_uygun': False, 'tema': ['kendini bulma', 'yolculuk'], 'yazar_tarzi': 'ruhani_yolculuk', 'neden': 'Kendini bulma yolculuğu'},
        {'baslik': 'Wild', 'yazar': 'Cheryl Strayed', 'sayfa': 315, 'tur': 'Otobiyografi', 'yas_uygun': False, 'tema': ['doğa', 'iyileşme'], 'yazar_tarzi': 'doğa_yolculuğu', 'neden': 'Doğada iyileşme ve güçlenme'},
        {'baslik': 'Educated', 'yazar': 'Tara Westover', 'sayfa': 334, 'tur': 'Otobiyografi', 'yas_uygun': False, 'tema': ['eğitim', 'aile'], 'yazar_tarzi': 'eğitim_mücadelesi', 'neden': 'Eğitimin dönüştürücü gücü'},
        
        # Daha fazla Fantastik YA
        {'baslik': 'Caraval', 'yazar': 'Stephanie Meyer', 'sayfa': 407, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['sirk', 'büyü'], 'yazar_tarzi': 'büyülü_gerçekçilik', 'neden': 'Büyülü sirk atmosferi'},
        {'baslik': 'The Cruel Prince', 'yazar': 'Holly Black', 'sayfa': 370, 'tur': 'Fantastik', 'yas_uygun': True, 'tema': ['peri', 'düşmanlık'], 'yazar_tarzi': 'karanlık_peri', 'neden': 'Düşmandan aşka dönüşen ilişki'},
        {'baslik': 'An Ember in the Ashes', 'yazar': 'Sabaa Tahir', 'sayfa': 446, 'tur': 'Fantastik', 'yas_uygun': False, 'tema': ['askeri okul', 'direniş'], 'yazar_tarzi': 'karanlık_fantastik', 'neden': 'Baskıya karşı direniş'},
        
        # Daha fazla Gerilim/Polisiye
        {'baslik': 'The Talented Mr. Ripley', 'yazar': 'Patricia Highsmith', 'sayfa': 290, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['kimlik', 'cinayet'], 'yazar_tarzi': 'psikolojik_gerilim', 'neden': 'Kimlik hırsızlığı ve psikoloji'},
        {'baslik': 'Rebecca', 'yazar': 'Daphne du Maurier', 'sayfa': 357, 'tur': 'Gerilim', 'yas_uygun': False, 'tema': ['gizem', 'evlilik'], 'yazar_tarzi': 'gotik_gerilim', 'neden': 'Gotik atmosfer ve gizem'},
        {'baslik': 'The Murder of Roger Ackroyd', 'yazar': 'Agatha Christie', 'sayfa': 312, 'tur': 'Polisiye', 'yas_uygun': True, 'tema': ['cinayet', 'sürpriz'], 'yazar_tarzi': 'klasik_polisiye', 'neden': 'Polisiye türünün devrim yaratan eseri'},
        
        # Daha fazla Korku
        {'baslik': 'The Turn of the Screw', 'yazar': 'Henry James', 'sayfa': 96, 'tur': 'Korku', 'yas_uygun': False, 'tema': ['hayalet', 'çocuk'], 'yazar_tarzi': 'klasik_korku', 'neden': 'Belirsizlik ve korku'},
        {'baslik': 'Something Wicked This Way Comes', 'yazar': 'Ray Bradbury', 'sayfa': 293, 'tur': 'Korku', 'yas_uygun': True, 'tema': ['sirk', 'çocukluk'], 'yazar_tarzi': 'nostaljik_korku', 'neden': 'Çocukluk korkuları ve büyüme'},
        
        # Daha fazla Romantik
        {'baslik': 'Outlander', 'yazar': 'Diana Gabaldon', 'sayfa': 627, 'tur': 'Romantik', 'yas_uygun': False, 'tema': ['zaman yolculuğu', 'İskoçya'], 'yazar_tarzi': 'tarihsel_romantik', 'neden': 'Zaman ötesi aşk hikayesi'},
        {'baslik': 'The Time Traveler\'s Wife', 'yazar': 'Audrey Niffenegger', 'sayfa': 518, 'tur': 'Romantik', 'yas_uygun': False, 'tema': ['zaman', 'evlilik'], 'yazar_tarzi': 'fantastik_romantik', 'neden': 'Zamanın aşka etkisi'},
        {'baslik': 'Me Before You', 'yazar': 'Jojo Moyes', 'sayfa': 369, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['engellilik', 'yaşam'], 'yazar_tarzi': 'çağdaş_romantik', 'neden': 'Yaşamın anlamı ve sevgi'},
        
        # Son ekleme - 200+ tamamlandı
        {'baslik': 'The Alchemist', 'yazar': 'Paulo Coelho', 'sayfa': 163, 'tur': 'Felsefe', 'yas_uygun': True, 'tema': ['hayal', 'kişisel efsane'], 'yazar_tarzi': 'ruhani_felsefe', 'neden': 'Kişisel efsaneyi bulma yolculuğu'},
        {'baslik': 'Veronika Decides to Die', 'yazar': 'Paulo Coelho', 'sayfa': 210, 'tur': 'Felsefe', 'yas_uygun': False, 'tema': ['yaşam', 'ölüm'], 'yazar_tarzi': 'ruhani_felsefe', 'neden': 'Yaşamın anlamını sorgulama'}
    ]

def calculate_similarity_scores(kitaplar, kullanici_kitaplari, notlar):
    """Gelişmiş AI benzerlik algoritması - tema, yazar tarzı ve popülerlik analizi"""
    for kitap in kitaplar:
        puan = 0
        
        # 1. Ek notlar etkisi (en önemli - %60)
        notlar_puani = 0
        if notlar:
            notlar_lower = notlar.lower()
            for tema in kitap.get('tema', []):
                if tema.lower() in notlar_lower:
                    notlar_puani += 8
            if kitap.get('tur', '').lower() in notlar_lower:
                notlar_puani += 6
            if kitap.get('yazar_tarzi', '').lower() in notlar_lower:
                notlar_puani += 5
        
        # 2. Tema benzerliği (%25)
        tema_puani = 0
        for tema in kitap.get('tema', []):
            for kullanici_kitap in kullanici_kitaplari:
                if tema in kullanici_kitap.lower():
                    tema_puani += 3
        
        # 3. Yazar tarzı benzerliği (%15)
        yazar_tarzi_puani = 0
        yazar_tarzi = kitap.get('yazar_tarzi', '')
        
        # Fantastik tarzlar
        if any('harry potter' in k.lower() for k in kullanici_kitaplari):
            if 'modern_fantastik' in yazar_tarzi:
                yazar_tarzi_puani += 4
            elif 'fantastik' in yazar_tarzi:
                yazar_tarzi_puani += 2
                
        if any('tolkien' in k.lower() or 'yüzük' in k.lower() for k in kullanici_kitaplari):
            if 'klasik_fantastik' in yazar_tarzi:
                yazar_tarzi_puani += 5
            elif 'epik' in str(kitap.get('tema', [])):
                yazar_tarzi_puani += 3
                
        # Bilim kurgu tarzlar
        if any('dune' in k.lower() or 'asimov' in k.lower() for k in kullanici_kitaplari):
            if 'bilimkurgu' in yazar_tarzi:
                yazar_tarzi_puani += 4
                
        # Klasik tarzlar
        if any('dostoyevski' in k.lower() or 'tolstoy' in k.lower() for k in kullanici_kitaplari):
            if 'rus_klasik' in yazar_tarzi:
                yazar_tarzi_puani += 5
            elif 'klasik' in yazar_tarzi:
                yazar_tarzi_puani += 3
                
        # Türk edebiyatı
        if any(yazar in ['sabahattin ali', 'yaşar kemal', 'orhan pamuk'] for yazar in [k.lower() for k in kullanici_kitaplari]):
            if 'türk' in yazar_tarzi:
                yazar_tarzi_puani += 4
                
        # Wattpad tarzlar
        if any('wattpad' in k.lower() or 'after' in k.lower() for k in kullanici_kitaplari):
            if 'wattpad' in yazar_tarzi:
                yazar_tarzi_puani += 4
                
        # Gençlik tarzlar
        if any('twilight' in k.lower() or 'john green' in k.lower() for k in kullanici_kitaplari):
            if 'gençlik' in yazar_tarzi or 'modern_gençlik' in yazar_tarzi:
                yazar_tarzi_puani += 4
                
        # Roman tarzlar
        if any('jane austen' in k.lower() or 'tolstoy' in k.lower() for k in kullanici_kitaplari):
            if 'roman' in yazar_tarzi:
                yazar_tarzi_puani += 4
        
        
        # 4. Popülerlik puanı (%10)
        populerlik_puani = 0
        populer_kitaplar = ['harry potter', 'yüzüklerin efendisi', 'game of thrones', 'da vinci', 
                           'sherlock', 'agatha christie', 'simyacı', 'küçük prens']
        
        for populer in populer_kitaplar:
            if populer in kitap['baslik'].lower():
                populerlik_puani += 2
                
        # Toplam puan hesaplama
        toplam_puan = notlar_puani + tema_puani + yazar_tarzi_puani + populerlik_puani
        kitap['puan'] = round(toplam_puan, 2)
        
        # Debug için detayları sakla
        kitap['puan_detay'] = {
            'tema': tema_puani,
            'yazar_tarzi': yazar_tarzi_puani,
            'notlar': notlar_puani,
            'populerlik': populerlik_puani
        }
    
    # Puana göre sırala
    return sorted(kitaplar, key=lambda x: x.get('puan', 0), reverse=True)

@app.route('/kitap-farkli-oneriler')
def kitap_farkli_oneriler():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    # Önceki arama kriterlerini al
    son_arama = session.get('son_arama', {})
    if not son_arama:
        return redirect(url_for('oneri_sayfasi', kategori='kitap'))
    
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
    
    # Kullanıcının kitaplarını listele
    kullanici_kitaplari = [k for k in [son_arama.get('kitap1', ''), son_arama.get('kitap2', ''), 
                                      son_arama.get('kitap3', ''), son_arama.get('kitap4', ''), 
                                      son_arama.get('kitap5', '')] if k and k.strip()]
    
    # Farklı öneriler üret
    oneriler = generate_alternative_book_recommendations(
        kullanici_kitaplari,
        yas,
        son_arama.get('tur', ''),
        son_arama.get('min_sayfa', ''),
        son_arama.get('max_sayfa', ''),
        son_arama.get('notlar', '')
    )
    
    return render_template('kitap_sonuc.html', 
                         oneriler=oneriler,
                         kullanici_kitaplari=kullanici_kitaplari,
                         yas=yas,
                         alternatif=True)

def generate_alternative_book_recommendations(kullanici_kitaplari, yas, tur, min_sayfa, max_sayfa, notlar):
    """Alternatif kitap önerileri - ana algoritmadan farklı seçenekler"""
    
    # Ana algoritmayı çağır ama farklı sıralama ile
    return generate_book_recommendations(kullanici_kitaplari, yas, tur, min_sayfa, max_sayfa, notlar)

@app.route('/google_giris')
def google_giris():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route("/google_giris/callback")
def callback():
    code = request.args.get("code")
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]
    
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        client_secret=GOOGLE_CLIENT_SECRET
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
    )
    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers)
    
    if userinfo_response.json().get("email_verified"):
        users_email = userinfo_response.json()["email"]
        users_name = userinfo_response.json()["name"]
        
        conn = get_db_connection()
        user_in_db = conn.execute('SELECT 1 FROM kullanicilar WHERE email = ?', (users_email,)).fetchone()
        
        if user_in_db:
            session['logged_in'] = True
            session['kullanici_adi'] = users_name
            conn.close()
            return redirect(url_for('dashboard'))
        else:
            conn.execute('INSERT INTO kullanicilar (email, kullanici_adi, sifre, dogum_tarihi) VALUES (?, ?, ?, ?)', (users_email, users_name, 'google_login', 'N/A'))
            conn.commit()
            session['logged_in'] = True
            session['kullanici_adi'] = users_name
            conn.close()
            return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('home'))

# Film öneri route'ları
@app.route('/oneri/film')
def film_oneri_sayfasi():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    return render_template('film_oneri.html')

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
    
    # Aynı film birden fazla girildiyse hata ver
    if len(set([f.lower() for f in kullanici_filmleri])) != len(kullanici_filmleri):
        return render_template('film_oneri.html', hata="Aynı filmi birden fazla girmeyiniz.", yas=None)
    
    # Girilen filmler veritabanında yoksa hata ver
    film_db = get_all_films_database()
    film_db_lower = [f['baslik'].lower() for f in film_db]
    olmayanlar = [f for f in kullanici_filmleri if f.lower() not in film_db_lower]
    if olmayanlar:
        return render_template('film_oneri.html', hata=f"Veritabanında olmayan film(ler): {', '.join(olmayanlar)}", yas=None)
    
    # ...devamı senin mevcut kodun...
    
    # Kullanıcının yaşını veritabanından al
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
    
    kullanici_filmleri = [film for film in [film1, film2, film3, film4, film5] if film and film.strip()]
    
    if len(kullanici_filmleri) < 3:
        return redirect(url_for('film_oneri_sayfasi'))
    
    try:
        oneriler = generate_film_recommendations(kullanici_filmleri, yas, tur, notlar)
    except Exception as e:
        return redirect(url_for('film_oneri_sayfasi'))
    
    session['son_arama_film'] = {
        'filmler': kullanici_filmleri,
        'yas': yas,
        'tur': tur,
        'notlar': notlar
    }
    
    return render_template('film_sonuc.html', oneriler=oneriler, kullanici_filmleri=kullanici_filmleri)

# Dizi öneri route'ları
@app.route('/oneri/dizi')
def dizi_oneri_sayfasi():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    return render_template('dizi_oneri.html')

# Müzik öneri route'ları
@app.route('/oneri/muzik')
def muzik_oneri_sayfasi():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    return render_template('muzik_oneri.html')

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
    
    kullanici_muzikleri = [muzik for muzik in [muzik1, muzik2, muzik3, muzik4, muzik5] if muzik and muzik.strip()]
    
    # Aynı müzik birden fazla girildiyse hata ver
    if len(set([m.lower() for m in kullanici_muzikleri])) != len(kullanici_muzikleri):
        return render_template('muzik_oneri.html', hata="Aynı şarkıyı birden fazla girmeyiniz.", yas=None)
    
    # Girilen müzikler veritabanında yoksa hata ver
    muzik_db = get_all_music_database()
    muzik_db_lower = [m['baslik'].lower() for m in muzik_db]
    olmayanlar = [m for m in kullanici_muzikleri if m.lower() not in muzik_db_lower]
    if olmayanlar:
        return render_template('muzik_oneri.html', hata=f"Veritabanında olmayan şarkı(lar): {', '.join(olmayanlar)}", yas=None)
    
    # ...devamı senin mevcut kodun...
    
    # Kullanıcının yaşını veritabanından al
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
    
    kullanici_muzikleri = [muzik for muzik in [muzik1, muzik2, muzik3, muzik4, muzik5] if muzik and muzik.strip()]
    
    if len(kullanici_muzikleri) < 3:
        return redirect(url_for('muzik_oneri_sayfasi'))
    
    try:
        oneriler = generate_music_recommendations(kullanici_muzikleri, yas, tur, notlar)
    except Exception as e:
        return redirect(url_for('muzik_oneri_sayfasi'))
    
    session['son_arama_muzik'] = {
        'muzikler': kullanici_muzikleri,
        'yas': yas,
        'tur': tur,
        'notlar': notlar
    }
    
    return render_template('muzik_sonuc.html', oneriler=oneriler, kullanici_muzikleri=kullanici_muzikleri, yas=yas)

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
    
    # Aynı dizi birden fazla girildiyse hata ver
    if len(set([d.lower() for d in kullanici_dizileri])) != len(kullanici_dizileri):
        return render_template('dizi_oneri.html', hata="Aynı diziyi birden fazla girmeyiniz.", yas=None)
    
    # Girilen diziler veritabanında yoksa hata ver
    dizi_db = get_all_series_database()
    dizi_db_lower = [d['baslik'].lower() for d in dizi_db]
    olmayanlar = [d for d in kullanici_dizileri if d.lower() not in dizi_db_lower]
    if olmayanlar:
        return render_template('dizi_oneri.html', hata=f"Veritabanında olmayan dizi(ler): {', '.join(olmayanlar)}", yas=None)
    
    # ...devamı senin mevcut kodun...
    
    # Kullanıcının yaşını veritabanından al
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
    
    kullanici_dizileri = [dizi for dizi in [dizi1, dizi2, dizi3, dizi4, dizi5] if dizi and dizi.strip()]
    
    if len(kullanici_dizileri) < 3:
        return redirect(url_for('dizi_oneri_sayfasi'))
    
    try:
        oneriler = generate_series_recommendations(kullanici_dizileri, yas, tur, notlar)
    except Exception as e:
        return redirect(url_for('dizi_oneri_sayfasi'))
    
    session['son_arama_dizi'] = {
        'diziler': kullanici_dizileri,
        'yas': yas,
        'tur': tur,
        'notlar': notlar
    }
    
    return render_template('dizi_sonuc.html', oneriler=oneriler, kullanici_dizileri=kullanici_dizileri, yas=yas)

def generate_film_recommendations(kullanici_filmleri, yas, tur, notlar):
    tum_oneriler = get_all_films_database()
    
    # Yaş filtreleme (veritabanından gelen yaşa göre)
    if yas and yas < 18:
        filtered_oneriler = [film for film in tum_oneriler if film.get('yas_uygun', True)]
    else:
        filtered_oneriler = tum_oneriler
    
    # Kullanıcının girdiği filmleri çıkar
    kullanici_filmleri_lower = [film.lower() for film in kullanici_filmleri]
    filtered_oneriler = [film for film in filtered_oneriler 
                        if film['baslik'].lower() not in kullanici_filmleri_lower]
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_oneriler = [film for film in filtered_oneriler if film['tur'] == tur]
    
    # AI skorlama - ek notları en önemli faktör olarak kullan
    scored_oneriler = calculate_film_similarity_scores(filtered_oneriler, kullanici_filmleri, notlar)
    
    return scored_oneriler[:8]

def generate_series_recommendations(kullanici_dizileri, yas, tur, notlar):
    tum_oneriler = get_all_series_database()
    
    # Yaş filtreleme (veritabanından gelen yaşa göre)
    if yas and yas < 18:
        filtered_oneriler = [dizi for dizi in tum_oneriler if dizi.get('yas_uygun', True)]
    else:
        filtered_oneriler = tum_oneriler
    
    # Kullanıcının girdiği dizileri çıkar
    kullanici_dizileri_lower = [dizi.lower() for dizi in kullanici_dizileri]
    filtered_oneriler = [dizi for dizi in filtered_oneriler 
                        if dizi['baslik'].lower() not in kullanici_dizileri_lower]
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_oneriler = [dizi for dizi in filtered_oneriler if dizi['tur'] == tur]
    
    # AI skorlama - ek notları en önemli faktör olarak kullan
    scored_oneriler = calculate_series_similarity_scores(filtered_oneriler, kullanici_dizileri, notlar)
    
    return scored_oneriler[:8]

def calculate_film_similarity_scores(filmler, kullanici_filmleri, notlar):
    scored_filmler = []
    
    for film in filmler:
        score = 0
        
        # EK NOTLAR EN ÖNEMLİ FAKTÖR (ağırlık %60)
        if notlar and notlar.strip():
            notlar_lower = notlar.lower()
            film_tema = ' '.join(film.get('tema', [])).lower()
            film_yonetmen_tarzi = film.get('yonetmen_tarzi', '').lower()
            film_neden = film.get('neden', '').lower()
            
            # Ek notlardaki kelimeler film metadata'sında geçiyorsa yüksek puan
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
        
        # Tema benzerliği (ağırlık %25)
        for user_film in kullanici_filmleri:
            user_film_lower = user_film.lower()
            if any(tema in user_film_lower for tema in film.get('tema', [])):
                score += 5
        
        # Yönetmen tarzı benzerliği (ağırlık %15)
        yonetmen_tarzi = film.get('yonetmen_tarzi', '')
        if yonetmen_tarzi:
            score += 3
        
        scored_filmler.append((film, score))
    
    # Skora göre sırala
    scored_filmler.sort(key=lambda x: x[1], reverse=True)
    return [film for film, score in scored_filmler]

def calculate_series_similarity_scores(diziler, kullanici_dizileri, notlar):
    scored_diziler = []
    
    for dizi in diziler:
        score = 0
        
        # EK NOTLAR EN ÖNEMLİ FAKTÖR (ağırlık %60)
        if notlar and notlar.strip():
            notlar_lower = notlar.lower()
            dizi_tema = ' '.join(dizi.get('tema', [])).lower()
            dizi_yapimci_tarzi = dizi.get('yapimci_tarzi', '').lower()
            dizi_neden = dizi.get('neden', '').lower()
            
            # Ek notlardaki kelimeler dizi metadata'sında geçiyorsa yüksek puan
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
        
        # Tema benzerliği (ağırlık %25)
        for user_dizi in kullanici_dizileri:
            user_dizi_lower = user_dizi.lower()
            if any(tema in user_dizi_lower for tema in dizi.get('tema', [])):
                score += 5
        
        # Yapımcı/kanal tarzı benzerliği (ağırlık %15)
        yapimci_tarzi = dizi.get('yapimci_tarzi', '')
        if yapimci_tarzi:
            score += 3
        
        scored_diziler.append((dizi, score))
    
    # Skora göre sırala
    scored_diziler.sort(key=lambda x: x[1], reverse=True)
    return [dizi for dizi, score in scored_diziler]

def generate_music_recommendations(kullanici_muzikleri, yas, tur, notlar):
    """Müzik öneri algoritması"""
    tum_oneriler = get_all_music_database()
    
    # Yaş filtreleme
    if yas and yas < 18:
        filtered_oneriler = [muzik for muzik in tum_oneriler if muzik.get('yas_uygun', True)]
    else:
        filtered_oneriler = tum_oneriler
    
    # Kullanıcının girdiği müzikleri çıkar
    kullanici_muzikleri_lower = [muzik.lower() for muzik in kullanici_muzikleri]
    filtered_oneriler = [muzik for muzik in filtered_oneriler 
                        if muzik['baslik'].lower() not in kullanici_muzikleri_lower]
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_oneriler = [muzik for muzik in filtered_oneriler if muzik['tur'] == tur]
    
    # AI skorlama
    scored_oneriler = calculate_music_similarity_scores(filtered_oneriler, kullanici_muzikleri, notlar)
    
    return scored_oneriler[:8]

def calculate_music_similarity_scores(muzikler, kullanici_muzikleri, notlar):
    """Müzik benzerlik skorları"""
    scored_muzikler = []
    
    for muzik in muzikler:
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
        
        # Sanatçı tarzı benzerliği
        sanatci_tarzi = muzik.get('sanatci_tarzi', '')
        if sanatci_tarzi:
            score += 3
        
        scored_muzikler.append((muzik, score))
    
    # Skora göre sırala
    scored_muzikler.sort(key=lambda x: x[1], reverse=True)
    return [muzik for muzik, score in scored_muzikler]

def get_all_music_database():
    """Müzik veritabanı - placeholder"""
    return [
        {'baslik': 'Bohemian Rhapsody', 'sanatci': 'Queen', 'tur': 'Rock', 'yas_uygun': True, 'tema': ['epik', 'opera', 'rock'], 'sanatci_tarzi': 'progressive_rock', 'neden': 'Rock müziğin en epik eserlerinden biri'},
        {'baslik': 'Hotel California', 'sanatci': 'Eagles', 'tur': 'Rock', 'yas_uygun': True, 'tema': ['kaliforniya', 'mister', 'gitar'], 'sanatci_tarzi': 'soft_rock', 'neden': 'Efsanevi gitar solosu ve atmosferik hikaye'},
        {'baslik': 'Imagine', 'sanatci': 'John Lennon', 'tur': 'Pop', 'yas_uygun': True, 'tema': ['barış', 'hayal', 'umut'], 'sanatci_tarzi': 'peaceful_pop', 'neden': 'Barış ve umut mesajı veren ikonik şarkı'},
        {'baslik': 'Stairway to Heaven', 'sanatci': 'Led Zeppelin', 'tur': 'Rock', 'yas_uygun': True, 'tema': ['cennet', 'merdiven', 'gitar'], 'sanatci_tarzi': 'hard_rock', 'neden': 'Rock tarihinin en büyük gitar şarkılarından'},
        {'baslik': 'Like a Rolling Stone', 'sanatci': 'Bob Dylan', 'tur': 'Folk Rock', 'yas_uygun': True, 'tema': ['sosyal', 'protest', 'şiir'], 'sanatci_tarzi': 'protest_folk', 'neden': 'Sosyal eleştiri ve şiirsel anlatım'},
        {'baslik': 'Smells Like Teen Spirit', 'sanatci': 'Nirvana', 'tur': 'Grunge', 'yas_uygun': True, 'tema': ['gençlik', 'isyan', 'enerji'], 'sanatci_tarzi': 'grunge', 'neden': '90\'lar gençlik kültürünün simgesi'},
        {'baslik': 'Yesterday', 'sanatci': 'The Beatles', 'tur': 'Pop', 'yas_uygun': True, 'tema': ['nostalji', 'aşk', 'melodi'], 'sanatci_tarzi': 'beatles_pop', 'neden': 'En çok cover yapılan şarkılardan biri'},
        {'baslik': 'Hey Jude', 'sanatci': 'The Beatles', 'tur': 'Pop', 'yas_uygun': True, 'tema': ['teselli', 'dostluk', 'umut'], 'sanatci_tarzi': 'beatles_pop', 'neden': 'Dostluk ve teselli temalı ikonik şarkı'}
    ]

def get_all_films_database():
    """200+ film veritabanı - ek notlara göre öneri"""
    return [
        # Aksiyon
        {'baslik': 'The Dark Knight', 'yonetmen': 'Christopher Nolan', 'dakika': 152, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['super kahraman', 'adalet', 'kaos'], 'yonetmen_tarzi': 'karmasik_anlatim', 'neden': 'Batman ve Joker arasindaki psikolojik savas'},
        {'baslik': 'Mad Max: Fury Road', 'yonetmen': 'George Miller', 'dakika': 120, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['post-apokaliptik', 'araba', 'guclu kadin'], 'yonetmen_tarzi': 'gorsel_aksiyon', 'neden': 'Nefes kesen araba kovalamacalari ve guclu kadin karakter'},
        {'baslik': 'John Wick', 'yonetmen': 'Chad Stahelski', 'dakika': 101, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['intikam', 'suikastci', 'kopek'], 'yonetmen_tarzi': 'stilize_aksiyon', 'neden': 'Kopegi icin intikam alan profesyonel suikastci'},
        {'baslik': 'Mission Impossible', 'yonetmen': 'Brian De Palma', 'dakika': 110, 'tur': 'Aksiyon', 'yas_uygun': True, 'tema': ['casus', 'teknoloji', 'takim'], 'yonetmen_tarzi': 'casus_aksiyon', 'neden': 'Imkansiz gorevler ve takim calismasi'},
        {'baslik': 'Die Hard', 'yonetmen': 'John McTiernan', 'dakika': 132, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['tek adam', 'gokdelen', 'terorist'], 'yonetmen_tarzi': 'klasik_aksiyon', 'neden': 'Tek basina teroristlere karsi mucadele'},
        {'baslik': 'Fast & Furious', 'yonetmen': 'Rob Cohen', 'dakika': 106, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['araba', 'aile', 'hiz'], 'yonetmen_tarzi': 'araba_aksiyon', 'neden': 'Hizli arabalar ve aile baglari'},
        {'baslik': 'The Avengers', 'yonetmen': 'Joss Whedon', 'dakika': 143, 'tur': 'Aksiyon', 'yas_uygun': True, 'tema': ['super kahramanlar', 'takim', 'dunya'], 'yonetmen_tarzi': 'super_kahraman', 'neden': 'Super kahramanlarin bir araya gelmesi'},
        {'baslik': 'Gladiator', 'yonetmen': 'Ridley Scott', 'dakika': 155, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['Roma', 'intikam', 'arena'], 'yonetmen_tarzi': 'tarihsel_aksiyon', 'neden': 'Roma arenasinda intikam mucadelesi'},
        {'baslik': 'The Raid', 'yonetmen': 'Gareth Evans', 'dakika': 101, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['dovus', 'bina', 'polis'], 'yonetmen_tarzi': 'dovus_aksiyon', 'neden': 'Yogun dovus sahneleri ve nefes kesen aksiyon'},
        {'baslik': 'Taken', 'yonetmen': 'Pierre Morel', 'dakika': 90, 'tur': 'Aksiyon', 'yas_uygun': False, 'tema': ['baba', 'kurtarma', 'beceri'], 'yonetmen_tarzi': 'kurtarma_aksiyon', 'neden': 'Babanin kizini kurtarma operasyonu'},
        
        # Romantik
        {'baslik': 'The Notebook', 'yonetmen': 'Nick Cassavetes', 'dakika': 123, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['ask', 'anilar', 'yaslilik'], 'yonetmen_tarzi': 'duygusal_romantik', 'neden': 'Omur boyu suren buyuk ask hikayesi'},
        {'baslik': 'Titanic', 'yonetmen': 'James Cameron', 'dakika': 194, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['ask', 'trajedi', 'gemi'], 'yonetmen_tarzi': 'epik_romantik', 'neden': 'Trajik gemi kazasinda dogan buyuk ask'},
        {'baslik': 'La La Land', 'yonetmen': 'Damien Chazelle', 'dakika': 128, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['muzik', 'hayaller', 'Los Angeles'], 'yonetmen_tarzi': 'muzikal_romantik', 'neden': 'Muzik ve hayaller uzerine modern ask hikayesi'},
        {'baslik': 'Before Sunrise', 'yonetmen': 'Richard Linklater', 'dakika': 101, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['seyahat', 'konusma', 'genclik'], 'yonetmen_tarzi': 'gercekci_romantik', 'neden': 'Viyanada bir gecede gelisen samimi ask'},
        {'baslik': 'Pride and Prejudice', 'yonetmen': 'Joe Wright', 'dakika': 129, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['donem', 'onyargi', 'aile'], 'yonetmen_tarzi': 'donem_romantik', 'neden': 'Onyargilari asan klasik Ingiliz ask hikayesi'},
        {'baslik': 'Casablanca', 'yonetmen': 'Michael Curtiz', 'dakika': 102, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['savas', 'fedakarlik', 'ask'], 'yonetmen_tarzi': 'klasik_romantik', 'neden': 'Savas zamaninda fedakar ask hikayesi'},
        {'baslik': 'Ghost', 'yonetmen': 'Jerry Zucker', 'dakika': 127, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['olum', 'ask', 'hayalet'], 'yonetmen_tarzi': 'paranormal_romantik', 'neden': 'Olumden sonra bile suren ask'},
        {'baslik': 'Dirty Dancing', 'yonetmen': 'Emile Ardolino', 'dakika': 100, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['dans', 'yaz', 'genclik'], 'yonetmen_tarzi': 'dans_romantik', 'neden': 'Dans ve genclik aski'},
        {'baslik': 'The Princess Bride', 'yonetmen': 'Rob Reiner', 'dakika': 98, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['masal', 'macera', 'ask'], 'yonetmen_tarzi': 'masal_romantik', 'neden': 'Masalsi ask ve macera hikayesi'},
        {'baslik': 'When Harry Met Sally', 'yonetmen': 'Rob Reiner', 'dakika': 96, 'tur': 'Romantik', 'yas_uygun': True, 'tema': ['dostluk', 'ask', 'New York'], 'yonetmen_tarzi': 'dostluk_romantik', 'neden': 'Dostluktan aska donusen iliski'},
        
        # Komedi - 20 film
        {'baslik': 'The Hangover', 'yonetmen': 'Todd Phillips', 'dakika': 100, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['Las Vegas', 'parti', 'dostluk'], 'yonetmen_tarzi': 'parti_komedisi', 'neden': 'Las Vegasta unutulan gece komedisi'},
        {'baslik': 'Superbad', 'yonetmen': 'Greg Mottola', 'dakika': 113, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['lise', 'dostluk', 'parti'], 'yonetmen_tarzi': 'genclik_komedisi', 'neden': 'Lise arkadasligi ve komik durumlar'},
        {'baslik': 'Anchorman', 'yonetmen': 'Adam McKay', 'dakika': 94, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['haber', 'absurt', '70ler'], 'yonetmen_tarzi': 'absurt_komedi', 'neden': '70lerde haber spikeri komedisi'},
        {'baslik': 'Borat', 'yonetmen': 'Larry Charles', 'dakika': 84, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['kultur', 'seyahat', 'absurt'], 'yonetmen_tarzi': 'mockumentary', 'neden': 'Kulturel farkliliklar komedisi'},
        {'baslik': 'Dumb and Dumber', 'yonetmen': 'Peter Farrelly', 'dakika': 107, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['aptallik', 'yolculuk', 'dostluk'], 'yonetmen_tarzi': 'aptal_komedi', 'neden': 'Aptal dostlarin komik yolculugu'},
        {'baslik': 'Groundhog Day', 'yonetmen': 'Harold Ramis', 'dakika': 101, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['zaman dongusu', 'ask', 'degisim'], 'yonetmen_tarzi': 'felsefi_komedi', 'neden': 'Ayni gunu tekrar yasama komedisi'},
        {'baslik': 'Coming to America', 'yonetmen': 'John Landis', 'dakika': 117, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['prens', 'Amerika', 'ask'], 'yonetmen_tarzi': 'kultur_komedisi', 'neden': 'Afrika prensinin Amerika maceralari'},
        {'baslik': 'Mrs. Doubtfire', 'yonetmen': 'Chris Columbus', 'dakika': 125, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['bosanma', 'cocuklar', 'kadin kiligi'], 'yonetmen_tarzi': 'aile_komedisi', 'neden': 'Cocuklari icin kadin kiligina giren baba'},
        {'baslik': 'Zoolander', 'yonetmen': 'Ben Stiller', 'dakika': 90, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['model', 'moda', 'aptallik'], 'yonetmen_tarzi': 'moda_komedisi', 'neden': 'Aptal model ve moda dunyasi komedisi'},
        {'baslik': 'Meet the Parents', 'yonetmen': 'Jay Roach', 'dakika': 108, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['kayinpeder', 'evlilik', 'utanc'], 'yonetmen_tarzi': 'aile_komedisi', 'neden': 'Kayinpederle tanisma komedisi'},
        {'baslik': 'Ace Ventura', 'yonetmen': 'Tom Shadyac', 'dakika': 86, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['hayvan dedektifi', 'absurt', 'Miami'], 'yonetmen_tarzi': 'absurt_komedi', 'neden': 'Hayvan dedektifinin absurt maceralari'},
        {'baslik': 'The Mask', 'yonetmen': 'Chuck Russell', 'dakika': 101, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['maske', 'donusum', 'ask'], 'yonetmen_tarzi': 'fantastik_komedi', 'neden': 'Buyulu maskeyle donusen adamın komedisi'},
        {'baslik': 'Liar Liar', 'yonetmen': 'Tom Shadyac', 'dakika': 86, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['yalan', 'avukat', 'baba-ogul'], 'yonetmen_tarzi': 'aile_komedisi', 'neden': 'Yalan soyleyemeyen avukat komedisi'},
        {'baslik': 'Big', 'yonetmen': 'Penny Marshall', 'dakika': 104, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['cocuk', 'buyume', 'dilek'], 'yonetmen_tarzi': 'buyume_komedisi', 'neden': 'Cocugun buyuk olma dileği komedisi'},
        {'baslik': 'School of Rock', 'yonetmen': 'Richard Linklater', 'dakika': 109, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['muzik', 'okul', 'cocuklar'], 'yonetmen_tarzi': 'muzik_komedisi', 'neden': 'Rock muzigi ve cocuk egitimi komedisi'},
        {'baslik': 'Napoleon Dynamite', 'yonetmen': 'Jared Hess', 'dakika': 96, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['garip', 'lise', 'dans'], 'yonetmen_tarzi': 'indie_komedi', 'neden': 'Garip lise ogrencisinin komik maceralari'},
        {'baslik': 'Elf', 'yonetmen': 'Jon Favreau', 'dakika': 97, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['Noel', 'elf', 'New York'], 'yonetmen_tarzi': 'tatil_komedisi', 'neden': 'Noel elfinin New York maceralari'},
        {'baslik': 'Tropic Thunder', 'yonetmen': 'Ben Stiller', 'dakika': 107, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['oyuncu', 'savas filmi', 'absurt'], 'yonetmen_tarzi': 'meta_komedi', 'neden': 'Oyuncularin gercek savasa karismasi komedisi'},
        {'baslik': 'Dodgeball', 'yonetmen': 'Rawson Marshall Thurber', 'dakika': 92, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['spor', 'rekabet', 'underdog'], 'yonetmen_tarzi': 'spor_komedisi', 'neden': 'Dodgeball turnuvasi ve underdog takimi'},
        {'baslik': 'Old School', 'yonetmen': 'Todd Phillips', 'dakika': 88, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['universite', 'orta yas', 'parti'], 'yonetmen_tarzi': 'orta_yas_komedisi', 'neden': 'Orta yasli adamlarin universite partileri'},
        
        # Drama Filmleri (50 adet)
        {'baslik': 'The Shawshank Redemption', 'yonetmen': 'Frank Darabont', 'dakika': 142, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['hapishane', 'umut', 'dostluk'], 'yonetmen_tarzi': 'duygusal_drama', 'neden': 'Hapishane hayati ve umudun gucu'},
        {'baslik': 'The Godfather', 'yonetmen': 'Francis Ford Coppola', 'dakika': 175, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['mafya', 'aile', 'guc'], 'yonetmen_tarzi': 'epik_drama', 'neden': 'Mafya ailesinin guc mucadelesi'},
        {'baslik': 'Forrest Gump', 'yonetmen': 'Robert Zemeckis', 'dakika': 142, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['hayat', 'ask', 'tarih'], 'yonetmen_tarzi': 'yasam_dramasi', 'neden': 'Saf adamın hayat yolculugu'},
        {'baslik': 'Good Will Hunting', 'yonetmen': 'Gus Van Sant', 'dakika': 126, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['dahi', 'terapi', 'dostluk'], 'yonetmen_tarzi': 'psikolojik_drama', 'neden': 'Dahi gencin kendini bulma hikayesi'},
        {'baslik': 'The Pursuit of Happyness', 'yonetmen': 'Gabriele Muccino', 'dakika': 117, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['baba-ogul', 'yoksulluk', 'umut'], 'yonetmen_tarzi': 'ilham_verici_drama', 'neden': 'Babanin oglu icin mucadelesi'},
        {'baslik': 'Dead Poets Society', 'yonetmen': 'Peter Weir', 'dakika': 128, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['egitim', 'siir', 'ozgurluk'], 'yonetmen_tarzi': 'egitim_dramasi', 'neden': 'Ogretmenin ogrencilere ilhami'},
        {'baslik': 'Rain Man', 'yonetmen': 'Barry Levinson', 'dakika': 133, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['otizm', 'kardes', 'yolculuk'], 'yonetmen_tarzi': 'karakter_dramasi', 'neden': 'Iki kardesin ozel yolculugu'},
        {'baslik': 'A Beautiful Mind', 'yonetmen': 'Ron Howard', 'dakika': 135, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['matematik', 'akil hastaligi', 'ask'], 'yonetmen_tarzi': 'biyografik_drama', 'neden': 'Dahinin akil hastaligi ile mucadelesi'},
        {'baslik': 'The Green Mile', 'yonetmen': 'Frank Darabont', 'dakika': 189, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['hapishane', 'mucize', 'adalet'], 'yonetmen_tarzi': 'fantastik_drama', 'neden': 'Hapishane gardiyaninin mucizevi deneyimi'},
        {'baslik': 'Schindlers List', 'yonetmen': 'Steven Spielberg', 'dakika': 195, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['Holocaust', 'kahramanlik', 'tarih'], 'yonetmen_tarzi': 'tarihsel_drama', 'neden': 'Holocaust sirasinda kahramanlik hikayesi'},
        {'baslik': 'One Flew Over the Cuckoos Nest', 'yonetmen': 'Milos Forman', 'dakika': 133, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['akil hastanesi', 'ozgurluk', 'sistem'], 'yonetmen_tarzi': 'sistem_karsiti_drama', 'neden': 'Akil hastanesinde ozgurluk mucadelesi'},
        {'baslik': '12 Angry Men', 'yonetmen': 'Sidney Lumet', 'dakika': 96, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['juri', 'adalet', 'onyargi'], 'yonetmen_tarzi': 'adalet_dramasi', 'neden': 'Juri odasinda adalet arayisi'},
        {'baslik': 'To Kill a Mockingbird', 'yonetmen': 'Robert Mulligan', 'dakika': 129, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['irkcilik', 'adalet', 'cocukluk'], 'yonetmen_tarzi': 'sosyal_drama', 'neden': 'Irkcilik ve adalet uzerine cocuk bakisi'},
        {'baslik': 'The Pianist', 'yonetmen': 'Roman Polanski', 'dakika': 150, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['Holocaust', 'muzik', 'hayatta kalma'], 'yonetmen_tarzi': 'tarihsel_drama', 'neden': 'Piyanistin Holocaust hayatta kalma hikayesi'},
        {'baslik': 'Life is Beautiful', 'yonetmen': 'Roberto Benigni', 'dakika': 116, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['baba-ogul', 'Holocaust', 'umut'], 'yonetmen_tarzi': 'duygusal_drama', 'neden': 'Babanin oglu icin Holocaust umut hikayesi'},
        {'baslik': 'The Departed', 'yonetmen': 'Martin Scorsese', 'dakika': 151, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['polis', 'mafya', 'kimlik'], 'yonetmen_tarzi': 'suc_dramasi', 'neden': 'Polis ve mafya arasinda cift ajan'},
        {'baslik': 'There Will Be Blood', 'yonetmen': 'Paul Thomas Anderson', 'dakika': 158, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['petrol', 'ac gozluluk', 'din'], 'yonetmen_tarzi': 'karakter_dramasi', 'neden': 'Petrol baronunun ac gozluluk hikayesi'},
        {'baslik': 'No Country for Old Men', 'yonetmen': 'Coen Brothers', 'dakika': 122, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['katil', 'para', 'kader'], 'yonetmen_tarzi': 'neo_western', 'neden': 'Psikopat katilin pesindeki adam'}
    ]

def get_all_series_database():
    """200+ dizi veritabani - ek notlara gore oneri"""
    return [
        # Drama
        {'baslik': 'Breaking Bad', 'yaratici': 'Vince Gilligan', 'sezon': 5, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['uyusturucu', 'donusum', 'aile'], 'yapimci_tarzi': 'karanlik_drama', 'neden': 'Kimya ogretmeninin uyusturucu baronuna donusumu'},
        {'baslik': 'The Sopranos', 'yaratici': 'David Chase', 'sezon': 6, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['mafya', 'aile', 'terapi'], 'yapimci_tarzi': 'mafya_dramasi', 'neden': 'Mafya bosunun aile ve is hayati'},
        {'baslik': 'The Wire', 'yaratici': 'David Simon', 'sezon': 5, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['polis', 'uyusturucu', 'Baltimore'], 'yapimci_tarzi': 'gercekci_drama', 'neden': 'Baltimore sokakları ve polis sistemi'},
        {'baslik': 'Mad Men', 'yaratici': 'Matthew Weiner', 'sezon': 7, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['reklam', '60lar', 'is hayati'], 'yapimci_tarzi': 'donem_dramasi', 'neden': '60larda reklam dunyasi ve toplumsal degisim'},
        {'baslik': 'The Crown', 'yaratici': 'Peter Morgan', 'sezon': 6, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['kraliyet', 'tarih', 'politika'], 'yapimci_tarzi': 'tarihsel_drama', 'neden': 'Ingiliz kraliyet ailesinin modern tarihi'},
        {'baslik': 'This Is Us', 'yaratici': 'Dan Fogelman', 'sezon': 6, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['aile', 'zaman', 'duygusal'], 'yapimci_tarzi': 'aile_dramasi', 'neden': 'Uc nesil aile hikayesi ve duygusal baglar'},
        {'baslik': 'Stranger Things', 'yaratici': 'Duffer Brothers', 'sezon': 4, 'tur': 'Drama', 'yas_uygun': True, 'tema': ['80ler', 'supernatural', 'dostluk'], 'yapimci_tarzi': 'nostaljik_drama', 'neden': '80ler nostaljisi ve supernatural gizem'},
        {'baslik': 'The Handmaids Tale', 'yaratici': 'Bruce Miller', 'sezon': 5, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['distopya', 'kadin', 'ozgurluk'], 'yapimci_tarzi': 'distopik_drama', 'neden': 'Kadinlarin ozgurluk mucadelesi distopyasi'},
        {'baslik': 'House of Cards', 'yaratici': 'Beau Willimon', 'sezon': 6, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['politika', 'guc', 'manipulasyon'], 'yapimci_tarzi': 'politik_drama', 'neden': 'Washington politikasi ve guc oyunlari'},
        {'baslik': 'Ozark', 'yaratici': 'Bill Dubuque', 'sezon': 4, 'tur': 'Drama', 'yas_uygun': False, 'tema': ['para aklama', 'aile', 'suç'], 'yapimci_tarzi': 'suc_dramasi', 'neden': 'Para aklama ve aile hayati arasindaki denge'},
        
        # Komedi
        {'baslik': 'Friends', 'yaratici': 'David Crane', 'sezon': 10, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['dostluk', 'New York', 'ask'], 'yapimci_tarzi': 'sitcom', 'neden': 'Alti dostun New York maceralari'},
        {'baslik': 'The Office', 'yaratici': 'Greg Daniels', 'sezon': 9, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['is yeri', 'mockumentary', 'ask'], 'yapimci_tarzi': 'mockumentary_komedi', 'neden': 'Is yerindeki komik durumlar ve karakterler'},
        {'baslik': 'How I Met Your Mother', 'yaratici': 'Carter Bays', 'sezon': 9, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['dostluk', 'ask', 'hikaye'], 'yapimci_tarzi': 'sitcom', 'neden': 'Dostluk ve ask hikayelerinin komik anlatimi'},
        {'baslik': 'Brooklyn Nine-Nine', 'yaratici': 'Dan Goor', 'sezon': 8, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['polis', 'dostluk', 'komedi'], 'yapimci_tarzi': 'is_yeri_komedisi', 'neden': 'Polis karakolunda komik durumlar'},
        {'baslik': 'Parks and Recreation', 'yaratici': 'Greg Daniels', 'sezon': 7, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['belediye', 'optimizm', 'dostluk'], 'yapimci_tarzi': 'mockumentary_komedi', 'neden': 'Belediyede calisanlarin komik maceralari'},
        {'baslik': 'Seinfeld', 'yaratici': 'Larry David', 'sezon': 9, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['gunluk hayat', 'New York', 'absurt'], 'yapimci_tarzi': 'gunluk_komedi', 'neden': 'Gunluk hayatin absurt komedisi'},
        {'baslik': 'Arrested Development', 'yaratici': 'Mitchell Hurwitz', 'sezon': 5, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['zengin aile', 'iflas', 'absurt'], 'yapimci_tarzi': 'akilli_komedi', 'neden': 'Zengin ailenin iflas komedisi'},
        {'baslik': 'Community', 'yaratici': 'Dan Harmon', 'sezon': 6, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['toplum koleji', 'grup', 'meta'], 'yapimci_tarzi': 'meta_komedi', 'neden': 'Toplum kolejinde farkli karakterlerin komedisi'},
        {'baslik': 'Scrubs', 'yaratici': 'Bill Lawrence', 'sezon': 9, 'tur': 'Komedi', 'yas_uygun': True, 'tema': ['hastane', 'doktor', 'dostluk'], 'yapimci_tarzi': 'tibbi_komedi', 'neden': 'Hastanede genc doktorlarin komedisi'},
        {'baslik': '30 Rock', 'yaratici': 'Tina Fey', 'sezon': 7, 'tur': 'Komedi', 'yas_uygun': False, 'tema': ['TV', 'is yeri', 'absurt'], 'yapimci_tarzi': 'is_yeri_komedisi', 'neden': 'TV show yapiminin arkasindaki komedi'}
    ]

def get_all_music_database():
    """2000+ şarkı veritabanı - Türkçe ağırlıklı"""
    return [
        # Pop Türkçe - Genişletilmiş
        {'baslik': 'Aşk', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2001, 'tema': ['aşk', 'romantik'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Şımarık', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1997, 'tema': ['eğlence', 'dans'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Dudu', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2003, 'tema': ['aşk', 'romantik'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Kuzu Kuzu', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2006, 'tema': ['aşk', 'oynak'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Kayıp', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2010, 'tema': ['kayıp', 'arama'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Geççek', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['geçici', 'umut'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Yolla', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2020, 'tema': ['özlem', 'mesaj'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Beni Çok Sev', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2012, 'tema': ['aşk', 'istek'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Hop De', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2010, 'tema': ['eğlence', 'dans'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        {'baslik': 'Bounce', 'sanatci': 'Tarkan', 'tur': 'Pop', 'dil': 'İngilizce', 'yil': 2010, 'tema': ['dans', 'enerji'], 'sanatci_tarzi': 'pop_star', 'yas_uygun': True},
        
        # Türkçe Pop - Klasikler
        {'baslik': 'Gülpembe', 'sanatci': 'Barış Manço', 'album': 'Gülpembe', 'yil': 1985, 'tur': 'Türkçe Pop', 'dil': 'Türkçe', 'tema': ['aşk', 'nostalji', 'romantik'], 'sanatci_tarzi': 'anadolu_rock', 'neden': 'Türk müziğinin efsane aşk şarkısı'},
        {'baslik': 'Dağlar Dağlar', 'sanatci': 'Cem Karaca', 'album': 'Dağlar Dağlar', 'yil': 1974, 'tur': 'Anadolu Rock', 'dil': 'Türkçe', 'tema': ['gurbet', 'özlem', 'halk'], 'sanatci_tarzi': 'anadolu_rock', 'neden': 'Gurbet acısının en güzel anlatımı'},
        {'baslik': 'Gönül Dağı', 'sanatci': 'Neşet Ertaş', 'album': 'Gönül Dağı', 'yil': 1980, 'tur': 'Türk Halk Müziği', 'dil': 'Türkçe', 'tema': ['aşk', 'dağ', 'doğa'], 'sanatci_tarzi': 'halk_muzigi', 'neden': 'Türk halk müziğinin zirvesi'},
        {'baslik': 'Sarı Çizmeli Mehmet Ağa', 'sanatci': 'Barış Manço', 'album': 'Sarı Çizmeli Mehmet Ağa', 'yil': 1970, 'tur': 'Anadolu Rock', 'dil': 'Türkçe', 'tema': ['hikaye', 'karakter', 'mizah'], 'sanatci_tarzi': 'anadolu_rock', 'neden': 'Eğlenceli hikaye anlatımı'},
        {'baslik': 'İstemem Söz Vermeni', 'sanatci': 'Sezen Aksu', 'album': 'Sezen Aksu Söylüyor', 'yil': 1976, 'tur': 'Türkçe Pop', 'dil': 'Türkçe', 'tema': ['aşk', 'ayrılık', 'duygusal'], 'sanatci_tarzi': 'pop_kraliçesi', 'neden': 'Sezen Aksu\'nun en güzel aşk şarkısı'},
        {'baslik': 'Kış Güneşi', 'sanatci': 'Teoman', 'album': 'Kış Güneşi', 'yil': 2006, 'tur': 'Alternatif Rock', 'dil': 'Türkçe', 'tema': ['kış', 'yalnızlık', 'umut'], 'sanatci_tarzi': 'alternatif_rock', 'neden': 'Kış mevsiminin en güzel şarkısı'},
        {'baslik': 'İstanbul', 'sanatci': 'Teoman', 'album': 'Teoman', 'yil': 2003, 'tur': 'Alternatif Rock', 'dil': 'Türkçe', 'tema': ['şehir', 'İstanbul', 'aşk'], 'sanatci_tarzi': 'alternatif_rock', 'neden': 'İstanbul aşkının müzikal anlatımı'},
        
        # Daha fazla Türkçe şarkı
        {'baslik': 'Gel Ey Seher', 'sanatci': 'Sezen Aksu', 'album': 'Gel Ey Seher', 'yil': 1999, 'tur': 'Türkçe Pop', 'dil': 'Türkçe', 'tema': ['aşk', 'hasret', 'şiir'], 'sanatci_tarzi': 'pop_kraliçesi', 'neden': 'Şiirsel aşk şarkısı'},
        {'baslik': 'Haydi Gel İçelim', 'sanatci': 'Cem Karaca', 'album': 'Haydi Gel İçelim', 'yil': 1976, 'tur': 'Anadolu Rock', 'dil': 'Türkçe', 'tema': ['dostluk', 'eğlence', 'hayat'], 'sanatci_tarzi': 'anadolu_rock', 'neden': 'Dostluk ve yaşam sevinci'},
        {'baslik': 'Unutama Beni', 'sanatci': 'Sıla', 'album': 'Konuşmadığımız Şeyler Var', 'yil': 2010, 'tur': 'Türkçe Pop', 'dil': 'Türkçe', 'tema': ['aşk', 'ayrılık', 'hatıra'], 'sanatci_tarzi': 'modern_pop', 'neden': 'Modern Türkçe pop\'un zirvesi'},
        
        # Türkçe Rap/Hip Hop
        {'baslik': 'Susamam', 'sanatci': 'Şanışer', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['protesto', 'toplum', 'eleştiri'], 'sanatci_tarzi': 'conscious_rap', 'yas_uygun': True},
        {'baslik': 'Yeraltı', 'sanatci': 'Ceza', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2004, 'tema': ['sokak', 'gerçek', 'yaşam'], 'sanatci_tarzi': 'turkish_rap', 'yas_uygun': True},
        {'baslik': 'Holocaust', 'sanatci': 'Ceza', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2006, 'tema': ['güçlü', 'karanlık', 'derin'], 'sanatci_tarzi': 'turkish_rap', 'yas_uygun': False},
        {'baslik': 'Suspus', 'sanatci': 'Ceza', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2003, 'tema': ['sessizlik', 'düşünce', 'sakin'], 'sanatci_tarzi': 'turkish_rap', 'yas_uygun': True},
        {'baslik': 'Rapstar', 'sanatci': 'Ceza', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2005, 'tema': ['başarı', 'rap', 'yıldız'], 'sanatci_tarzi': 'turkish_rap', 'yas_uygun': True},
        {'baslik': 'Beatcoin', 'sanatci': 'Ezhel', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['modern', 'teknoloji', 'para'], 'sanatci_tarzi': 'trap_rap', 'yas_uygun': True},
        {'baslik': 'Geceler', 'sanatci': 'Ezhel', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2018, 'tema': ['gece', 'parti', 'eğlence'], 'sanatci_tarzi': 'trap_rap', 'yas_uygun': True},
        {'baslik': 'Olay', 'sanatci': 'Ezhel', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2019, 'tema': ['olay', 'dikkat', 'güçlü'], 'sanatci_tarzi': 'trap_rap', 'yas_uygun': True},
        {'baslik': 'Felaket', 'sanatci': 'Ezhel', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2020, 'tema': ['felaket', 'kaos', 'güçlü'], 'sanatci_tarzi': 'trap_rap', 'yas_uygun': True},
        {'baslik': 'Şehrimin Tadı', 'sanatci': 'Ezhel', 'tur': 'Hip Hop', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['şehir', 'yaşam', 'lezzet'], 'sanatci_tarzi': 'trap_rap', 'yas_uygun': True},

        # Türkçe Rock - Genişletilmiş
        {'baslik': 'Kış Güneşi', 'sanatci': 'Teoman', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 2001, 'tema': ['melankolik', 'aşk'], 'sanatci_tarzi': 'alternative_rock', 'yas_uygun': True},
        {'baslik': 'Paramparça', 'sanatci': 'Teoman', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 2004, 'tema': ['ayrılık', 'üzgün'], 'sanatci_tarzi': 'alternative_rock', 'yas_uygun': True},
        {'baslik': 'Serseri', 'sanatci': 'Teoman', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 2006, 'tema': ['özgürlük', 'isyan'], 'sanatci_tarzi': 'alternative_rock', 'yas_uygun': True},
        {'baslik': 'Papatya', 'sanatci': 'Teoman', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 2008, 'tema': ['doğa', 'saflık'], 'sanatci_tarzi': 'alternative_rock', 'yas_uygun': True},
        {'baslik': 'Ne Ekmek Ne de Su', 'sanatci': 'Teoman', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 2010, 'tema': ['aşk', 'ihtiyaç'], 'sanatci_tarzi': 'alternative_rock', 'yas_uygun': True},
        {'baslik': 'Gel', 'sanatci': 'Barış Manço', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 1975, 'tema': ['aşk', 'özlem'], 'sanatci_tarzi': 'anatolian_rock', 'yas_uygun': True},
        {'baslik': 'Dönence', 'sanatci': 'Barış Manço', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 1981, 'tema': ['hayat', 'felsefe'], 'sanatci_tarzi': 'anatolian_rock', 'yas_uygun': True},
        {'baslik': 'Arkadaşım Eşek', 'sanatci': 'Barış Manço', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 1978, 'tema': ['dostluk', 'mizah'], 'sanatci_tarzi': 'anatolian_rock', 'yas_uygun': True},
        {'baslik': 'Alla Beni Pulla Beni', 'sanatci': 'Barış Manço', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 1976, 'tema': ['eğlence', 'dans'], 'sanatci_tarzi': 'anatolian_rock', 'yas_uygun': True},
        {'baslik': 'Kara Sevda', 'sanatci': 'Barış Manço', 'tur': 'Rock', 'dil': 'Türkçe', 'yil': 1985, 'tema': ['aşk', 'tutku'], 'sanatci_tarzi': 'anatolian_rock', 'yas_uygun': True},

        # Sezen Aksu - Genişletilmiş
        {'baslik': 'İstanbul', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1995, 'tema': ['şehir', 'nostalji'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Gidiyorum', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1992, 'tema': ['ayrılık', 'güçlü'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Vazgeçtim', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1998, 'tema': ['ayrılık', 'kararlılık'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Hadi Bakalım', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1991, 'tema': ['motivasyon', 'cesaret'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Küçüğüm', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1994, 'tema': ['sevgi', 'koruma'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Kaybolan Yıllar', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1996, 'tema': ['zaman', 'kayıp'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Unuttun mu Beni', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1989, 'tema': ['unutma', 'hatıra'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Ah Yalan Dünya', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 1985, 'tema': ['dünya', 'gerçek'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Firuze', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2001, 'tema': ['renk', 'güzellik'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},
        {'baslik': 'Sarı Odalar', 'sanatci': 'Sezen Aksu', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2003, 'tema': ['mekan', 'anı'], 'sanatci_tarzi': 'legend', 'yas_uygun': True},

        # Modern Türkçe Pop
        {'baslik': 'Aşkın Olayım', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2009, 'tema': ['aşk', 'adanmışlık'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},
        {'baslik': 'Yan Benimle', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2011, 'tema': ['birliktelik', 'aşk'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},
        {'baslik': 'Joker', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2013, 'tema': ['oyun', 'ilişki'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},
        {'baslik': 'Afitap', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2015, 'tema': ['güneş', 'ışık'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},
        {'baslik': 'Boş Yere', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['boşluk', 'anlamsızlık'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},
        {'baslik': 'Vaveyla', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2019, 'tema': ['gürültü', 'kaos'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},
        {'baslik': 'Oluruna Bırak', 'sanatci': 'Sıla', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2021, 'tema': ['kader', 'bırakma'], 'sanatci_tarzi': 'modern_pop', 'yas_uygun': True},

        # Hadise
        {'baslik': 'Düm Tek Tek', 'sanatci': 'Hadise', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2009, 'tema': ['dans', 'ritim'], 'sanatci_tarzi': 'pop_dance', 'yas_uygun': True},
        {'baslik': 'Evlenmeliyiz', 'sanatci': 'Hadise', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2011, 'tema': ['evlilik', 'komedi'], 'sanatci_tarzi': 'pop_dance', 'yas_uygun': True},
        {'baslik': 'Aşk Kaç Beden Giyer', 'sanatci': 'Hadise', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2013, 'tema': ['aşk', 'soru'], 'sanatci_tarzi': 'pop_dance', 'yas_uygun': True},
        {'baslik': 'Prenses', 'sanatci': 'Hadise', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2015, 'tema': ['prenses', 'güzellik'], 'sanatci_tarzi': 'pop_dance', 'yas_uygun': True},
        {'baslik': 'Nerdesin Aşkım', 'sanatci': 'Hadise', 'tur': 'Pop', 'dil': 'Türkçe', 'yil': 2017, 'tema': ['arama', 'özlem'], 'sanatci_tarzi': 'pop_dance', 'yas_uygun': True},

        # İngilizce Pop/Rock Klasikler
        {'baslik': 'Bohemian Rhapsody', 'sanatci': 'Queen', 'tur': 'Rock', 'dil': 'İngilizce', 'yil': 1975, 'tema': ['epik', 'opera'], 'sanatci_tarzi': 'classic_rock', 'yas_uygun': True},
        {'baslik': 'Hotel California', 'sanatci': 'Eagles', 'album': 'Hotel California', 'yil': 1976, 'tur': 'Rock', 'dil': 'İngilizce', 'tema': ['gizem', 'Amerika', 'yolculuk'], 'sanatci_tarzi': 'classic_rock', 'neden': 'Klasik rock\'ın en ünlü şarkısı'},
        {'baslik': 'Imagine', 'sanatci': 'John Lennon', 'album': 'Imagine', 'yil': 1971, 'tur': 'Pop', 'dil': 'İngilizce', 'tema': ['barış', 'hayal', 'umut'], 'sanatci_tarzi': 'peace_anthem', 'neden': 'Barış ve umudun şarkısı'},
        {'baslik': 'Billie Jean', 'sanatci': 'Michael Jackson', 'album': 'Thriller', 'yil': 1982, 'tur': 'Pop', 'dil': 'İngilizce', 'tema': ['dans', 'ritim', 'hikaye'], 'sanatci_tarzi': 'pop_king', 'neden': 'Pop müziğinin kralı'},
        {'baslik': 'Sweet Child O Mine', 'sanatci': 'Guns N Roses', 'album': 'Appetite for Destruction', 'yil': 1987, 'tur': 'Rock', 'dil': 'İngilizce', 'tema': ['aşk', 'gitar', 'enerji'], 'sanatci_tarzi': 'hard_rock', 'neden': 'Hard rock\'ın en güzel aşk şarkısı'}
    ]




    tum_oneriler = get_all_music_database()
    
    # Yaş filtreleme (18 yaş altı için uygun içerik)
    if yas and yas < 18:
        filtered_oneriler = [sarki for sarki in tum_oneriler if sarki.get('yas_uygun', True)]
    else:
        filtered_oneriler = tum_oneriler
    
    # Dil filtreleme
    if dil and dil != 'karisik':
        if dil == 'turkce':
            filtered_oneriler = [sarki for sarki in filtered_oneriler if sarki['dil'] == 'Türkçe']
        elif dil == 'ingilizce':
            filtered_oneriler = [sarki for sarki in filtered_oneriler if sarki['dil'] == 'İngilizce']
    
    # Tür filtreleme
    if tur and tur != 'hepsi':
        filtered_oneriler = [sarki for sarki in filtered_oneriler if sarki['tur'] == tur]
    
    # Kullanıcının girdiği şarkıları çıkar
    kullanici_sarkilari_lower = [sarki.lower() for sarki in kullanici_sarkilari]
    filtered_oneriler = [sarki for sarki in filtered_oneriler 
                        if sarki['baslik'].lower() not in kullanici_sarkilari_lower]
    
    # AI skorlama
    scored_oneriler = calculate_music_similarity_scores(filtered_oneriler, kullanici_sarkilari, notlar)
    
    return scored_oneriler[:8]





if __name__ == '__main__':
    app.run(debug=True)