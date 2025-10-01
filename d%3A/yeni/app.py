// ... existing code ...
@app.route('/dashboard')
def dashboard():
    if 'logged_in' in session:
        # Kullanıcı bilgisini ve yaşını şablona ilet (profil için)
        kullanici_adi = session.get('kullanici_adi')
        conn = get_db_connection()
        row = None
        if conn:
            cur = None
            try:
                cur = conn.cursor()
                cur.execute('SELECT kullanici_adi, dogum_tarihi, email FROM kullanicilar WHERE kullanici_adi = %s', (kullanici_adi,))
                raw_row = cur.fetchone()
                if raw_row:
                    columns = ['kullanici_adi', 'dogum_tarihi', 'email']
                    row = dict(zip(columns, raw_row))
            except Exception as e:
                app.logger.error(f"Dashboard veritabanı hatası: {e}")
            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
        yas = None
        if row and row['dogum_tarihi'] and row['dogum_tarihi'] != 'N/A':
            try:
@app.route('/kitap-oneri-al', methods=['POST'])
def kitap_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    if len(kullanici_kitaplari) < 3:
        return render_template('kitap_oneri.html', hata="En az 3 roman girmelisiniz.", yas=None, son_arama={})
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = None
    if conn:
        cur = None
        try:
            cur = conn.cursor()
            query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?'
            params = (session['kullanici_adi'],)

            # Use %s for psycopg2
            if type(conn).__module__ == 'psycopg2._psycopg':
                query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = %s'
            
            cur.execute(query, params)
            raw_row = cur.fetchone()
            if raw_row:
                kullanici = {'dogum_tarihi': raw_row[0]}

        except Exception as e:
            app.logger.error(f"DB error in kitap_oneri_al: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
@app.route('/film-oneri-al', methods=['POST'])
def film_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    if len(kullanici_filmleri) < 3:
        return render_template('film_oneri.html', hata="En az 3 film girmelisiniz.", yas=None)
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = None
    if conn:
        cur = None
        try:
            cur = conn.cursor()
            query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?'
            params = (session['kullanici_adi'],)

            if type(conn).__module__ == 'psycopg2._psycopg':
                query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = %s'
            
            cur.execute(query, params)
            raw_row = cur.fetchone()
            if raw_row:
                kullanici = {'dogum_tarihi': raw_row[0]}

        except Exception as e:
            app.logger.error(f"DB error in film_oneri_al: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
@app.route('/dizi-oneri-al', methods=['POST'])
def dizi_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    if len(kullanici_dizileri) < 3:
        return render_template('dizi_oneri.html', hata="En az 3 dizi girmelisiniz.", yas=None)
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = None
    if conn:
        cur = None
        try:
            cur = conn.cursor()
            query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?'
            params = (session['kullanici_adi'],)

            if type(conn).__module__ == 'psycopg2._psycopg':
                query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = %s'
            
            cur.execute(query, params)
            raw_row = cur.fetchone()
            if raw_row:
                kullanici = {'dogum_tarihi': raw_row[0]}

        except Exception as e:
            app.logger.error(f"DB error in dizi_oneri_al: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
            dogum_yili = int(kullanici['dogum_tarihi'].split('-')[0])
@app.route('/muzik-oneri-al', methods=['POST'])
def muzik_oneri_al():
    if 'logged_in' not in session:
        return redirect(url_for('home'))
    
    if len(kullanici_muzikleri) < 3:
        return render_template('muzik_oneri.html', hata="En az 3 şarkı girmelisiniz.", yas=None)
    
    # Kullanıcının yaşını al
    conn = get_db_connection()
    kullanici = None
    if conn:
        cur = None
        try:
            cur = conn.cursor()
            query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = ?'
            params = (session['kullanici_adi'],)

            if type(conn).__module__ == 'psycopg2._psycopg':
                query = 'SELECT dogum_tarihi FROM kullanicilar WHERE kullanici_adi = %s'
            
            cur.execute(query, params)
            raw_row = cur.fetchone()
            if raw_row:
                kullanici = {'dogum_tarihi': raw_row[0]}

        except Exception as e:
            app.logger.error(f"DB error in muzik_oneri_al: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    yas = None
    if kullanici and kullanici['dogum_tarihi'] != 'N/A':
        try:
@app.route('/giris', methods=['POST'])
def giris():
    email = request.form['email']
    sifre = request.form['sifre']
    beni_hatirla = request.form.get('beni_hatirla')
    
    if not email or not sifre:
        return render_template('index.html', hata="Lütfen tüm alanları doldurunuz.")
    
    conn = get_db_connection()
    kullanici = None
    if conn:
        cur = None
        try:
            cur = conn.cursor()
            cur.execute('SELECT * FROM kullanicilar WHERE email = %s AND sifre = %s', (email, sifre))

            raw_row = cur.fetchone()
            if raw_row:
                columns = [desc[0] for desc in cur.description]
                kullanici = dict(zip(columns, raw_row))
        except Exception as e:
            app.logger.error(f"Giriş veritabanı hatası: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                 conn.close()

    if kullanici:
        session['logged_in'] = True
// ... existing code ...