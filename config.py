import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask Configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'change-this-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() in ['true', '1', 'yes']
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    
    # SendGrid Email Configuration
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')
    SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL', '')
    
    # Eski email config (backup için kalsın)
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', '')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', '')
    
    # Google OAuth Configuration  
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    # Spotify API Configuration
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')
    
    # API Keys
    TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')
    GOOGLE_BOOKS_API_KEY = os.getenv('GOOGLE_BOOKS_API_KEY', '')
    HUGGING_FACE_TOKEN = os.getenv('HUGGING_FACE_TOKEN', '')
    LASTFM_API_KEY = os.getenv('LASTFM_API_KEY', '')
    
    @property
    def has_email_config(self):
        # SendGrid varsa onu kullan, yoksa eski sistemi dene
        return bool(self.SENDGRID_API_KEY and self.SENDGRID_FROM_EMAIL) or \
               bool(self.SENDER_EMAIL and self.SENDER_PASSWORD)
    
    @property
    def has_sendgrid(self):
        return bool(self.SENDGRID_API_KEY and self.SENDGRID_FROM_EMAIL)
    
    @property  
    def has_google_oauth(self):
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)
    
    @property
    def has_spotify_config(self):
        return bool(self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET)
    
    @property
    def has_tmdb_api(self):
        return bool(self.TMDB_API_KEY)
    
    @property
    def has_google_books_api(self):
        return bool(self.GOOGLE_BOOKS_API_KEY)
        
    @property
    def has_hugging_face_api(self):
        return bool(self.HUGGING_FACE_TOKEN)
        
    @property
    def has_lastfm_api(self):
        return bool(self.LASTFM_API_KEY)

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
    # Security headers for production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

# Configuration selector
config = {
    'development': Config,
    'production': ProductionConfig,
    'default': Config
}