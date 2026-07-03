import requests
import pdfplumber
import io

def kap_pdf_metin_oku(pdf_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    print("KAP'tan PDF dosyası çekiliyor...")
    response = requests.get(pdf_url, headers=headers)
    
    if response.status_code == 200:
        try:
            pdf_dosyasi = io.BytesIO(response.content)
            
            with pdfplumber.open(pdf_dosyasi) as pdf:
                print(f"✅ PDF indirildi. Toplam {len(pdf.pages)} sayfa metin olarak okunuyor...\n")
                
                # Sayfaları tek tek gezip içindeki yazıları çekiyoruz
                for sayfa_no, page in enumerate(pdf.pages):
                    metin = page.extract_text()
                    
                    if metin:
                        print(f"--- SAYFA {sayfa_no + 1} ---")
                        print(metin)
                        print("-" * 50)
                        
        except Exception as e:
            print(f"❌ PDF okunurken bir hata oluştu: {e}")
    else:
        print(f"❌ Dosyaya ulaşılamadı. Hata Kodu: {response.status_code}")

# GOH fonu PDF linki
test_linki = "https://www.kap.org.tr/tr/api/file/download/4028328c9cc9d177019ccdb8c459061a" 
kap_pdf_metin_oku(test_linki)