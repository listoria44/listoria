import sqlite3

def guncelle():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE kullanicilar ADD COLUMN kullanici_adi TEXT;")
        conn.commit()
        print("Veritabanı başarıyla güncellendi. 'kullanici_adi' sütunu eklendi.")
    except sqlite3.OperationalError:
        print("Hata: 'kullanici_adi' sütunu zaten mevcut.")
    finally:
        conn.close()

if __name__ == "__main__":
    guncelle()