import streamlit as st
import requests
import pdfplumber
import io
import pandas as pd
import re
import json
import os
import time
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

try:
    import yfinance as yf
    YF_HAZIR = True
except ImportError:
    YF_HAZIR = False

# Sayfa Ayarları
st.set_page_config(page_title="KAP Fon Analiz Pro", layout="wide")

# ==========================================
# VERİ YÖNETİMİ
# ==========================================
if "ozet_df" not in st.session_state: st.session_state.ozet_df = None
if "bulunan_fonlar" not in st.session_state: st.session_state.bulunan_fonlar = []

def json_oku():
    if os.path.exists("fon_gecmisi.json"):
        with open("fon_gecmisi.json", "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def piyasa_verisi_oku():
    if os.path.exists("piyasa_verileri.json"):
        with open("piyasa_verileri.json", "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def piyasa_verisi_kaydet(veri):
    with open("piyasa_verileri.json", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=4)

def yf_toplam_lot_cek(hisse_kodu):
    try:
        ticker = yf.Ticker(f"{hisse_kodu}.IS")
        lot = ticker.info.get("sharesOutstanding", 0)
        return lot if lot else 0
    except:
        return 0

def temizle_sayi(metin):
    metin = str(metin).replace('%', '')
    metin = re.sub(r'[^\d.,-]', '', metin)
    if not metin or metin in ['-', '.', ',']: return 0.0
    son_nokta, son_virgul = metin.rfind('.'), metin.rfind(',')
    if son_virgul > son_nokta: metin = metin.replace('.', '').replace(',', '.')
    elif son_nokta > son_virgul: metin = metin.replace(',', '')
    try: return float(metin)
    except: return 0.0

def tablo_yuksekligi_hesapla(df):
    satir_sayisi = len(df)
    return (satir_sayisi * 36) + 45

# ==========================================
# EXCEL'DEN FON LİSTESİ ÇEKME
# ==========================================
def excel_fon_listesi_cek(dosya_yolu):
    if not os.path.exists(dosya_yolu):
        return [], f"Dosya bulunamadı: {dosya_yolu}"
    try:
        df = pd.read_excel(dosya_yolu, header=1)
        if "Fon Kodu" in df.columns:
            kodlar = df["Fon Kodu"].dropna().astype(str).str.strip().unique().tolist()
            temiz_kodlar = [k.upper() for k in kodlar if len(k) == 3 and k.isalnum()]
            return sorted(temiz_kodlar), "Başarılı"
        else:
            return [], "Dosyada 'Fon Kodu' bulunamadı."
    except Exception as e:
        return [], f"Excel okuma hatası: {e}"

# ==========================================
# ROBOT VE PDF ANALİZ MOTORLARI
# ==========================================
def chrome_ayarlarini_getir():
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--start-maximized')
    options.add_argument('--page-load-strategy=eager') 
    return options

def fintables_link_yakala(driver, fon_kodu):
    try:
        driver.set_page_load_timeout(15) 
        driver.get(f"https://fintables.com/fonlar/{fon_kodu.upper()}/akis")
        time.sleep(3)
        try:
            cerez = driver.find_element(By.XPATH, "//button[contains(., 'Kabul') or contains(., 'Anladım')]")
            driver.execute_script("arguments[0].click();", cerez)
        except: pass
        try:
            rapor = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Portföy Dağılım Raporu')]")))
            driver.execute_script("arguments[0].click();", rapor)
            time.sleep(3)
            html = driver.page_source
            dosya = re.findall(r'[A-Z0-9_.-]+\.pdf', html)
            if dosya: return f"https://storage.fintables.com/media/uploads/kap-attachments/{dosya[0]}", "Başarılı"
            return None, "Haber bulundu ama PDF dosyası yok."
        except: 
            return None, "Rapor haberi sitede bulunamadı."
    except Exception as e:
        return None, f"Sayfa yüklenemedi veya zaman aşımı."

def pdf_analiz_et(url):
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if res.status_code != 200: return None, f"PDF sunucusu hata verdi ({res.status_code})"
    except Exception as e:
        return None, "PDF indirilirken bağlantı koptu veya çok yavaş."

    hisseler = []
    try:
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            son_kod = "" # HAFIZA: Gördüğü son hisse kodunu aklında tutar
            
            for sayfa in pdf.pages:
                metin = sayfa.extract_text()
                if not metin: continue
                
                for satir in metin.split('\n'):
                    kelimeler = satir.split()
                    if not kelimeler: continue
                    
                    # 1. Hafıza Güncellemesi (Satır başında hisse kodu benzeri kelime varsa kaydet)
                    ilk = kelimeler[0].replace(".E", "").strip()
                    if re.match(r'^[A-Z0-9İ]{3,7}$', ilk) and not ilk.isdigit():
                        yasakli_kelimeler = ["FON", "TOPLAM", "GRUP", "NAKIT", "REPO", "TUREV", "VIOP", "ISIN", "PAY", "BORC", "YAT", "BPP", "KIRA", "TL", "TRY", "USD", "EUR", "A.S.", "A.S", "AS"]
                        if ilk not in yasakli_kelimeler:
                            son_kod = ilk

                    # 2. Tam 12 Haneli Kesin ISIN Kodu Yakalama
                    isin_match = re.search(r'TR[A-Z0-9]{10}', satir)
                    
                    if isin_match:
                        isin_kodu = isin_match.group(0)
                        
                        # 3. Hisse Kodunu Belirleme (Önce aynı satıra bak, yoksa hafızadakini kullan)
                        kod = ""
                        for k in kelimeler[:4]:
                            temiz = k.replace(".E", "").strip()
                            if re.match(r'^[A-Z0-9İ]{3,7}$', temiz) and not temiz.isdigit() and temiz not in yasakli_kelimeler:
                                kod = temiz
                                break
                                
                        if not kod:
                            kod = son_kod
                            
                        if not kod: continue # Hala bulamadıysa atla
                        
                        # 4. Satırı Ameliyat Masasına Al (ISIN sonrasındaki sayıları topla)
                        sag_taraf = satir[satir.find(isin_kodu) + len(isin_kodu):]
                        sayilar = []
                        for sk in sag_taraf.split():
                            if re.match(r'\d{2}[./-]\d{2}[./-]\d{2,4}', sk): continue # Tarihleri yoksay
                            num = temizle_sayi(sk)
                            if num != 0: sayilar.append(num)
                            
                        if len(sayilar) >= 1:
                            lot = sayilar[0]
                            oran = sayilar[-1] if len(sayilar) > 1 else 0.0
                            
                            # 5. AKILLI FİLTRE: Lot eksi olmamalı VE Oran 100'den küçük olmalı (Takasbank ID'lerini engeller)
                            if lot > 0 and oran <= 100.0:
                                hisseler.append({"Hisse": kod, "Lot": lot, "Oran": oran})
                                
    except Exception as e:
        return None, f"PDF dosyası okunamayan formatta."

    if not hisseler: return None, "PDF okundu ama geçerli ana portföy tablosu bulunamadı."
    
    df = pd.DataFrame(hisseler).groupby("Hisse").agg({"Lot":"sum", "Oran":"sum"}).reset_index()
    return df.sort_values("Oran", ascending=False), "Başarılı"

# ==========================================
# STREAMLIT ARAYÜZÜ VE SEKMELER
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📥 Akıllı Tarayıcı", 
    "📂 Kayıtlı Portföyler", 
    "⚖️ Karşılaştırma", 
    "🔥 Piyasa Liderleri", 
    "🔍 Nokta Atışı Hisse"
])

kolon_yapisi = {
    "Hisse": st.column_config.TextColumn("Hisse Kodu", width="medium"),
    "Lot": st.column_config.NumberColumn("Lot Miktarı", width="medium", format="%d"),
    "Oran": st.column_config.NumberColumn("Portföy Oranı (%)", width="medium")
}

# ------------------------------------------
# SEKME 1: AKILLI TARAYICI
# ------------------------------------------
with tab1:
    mod = st.radio("Tarama Modu Seçin:", ["🎯 Tekli", "📋 Virgülle Çoklu", "🚀 Excel'den Toplu Tarama"])
    
    if mod == "🎯 Tekli":
        k = st.text_input("Fon Kodu (Örn: TTE):").upper()
        if st.button("Hızlı Analiz"):
            if k:
                d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_ayarlarini_getir())
                link, mesaj = fintables_link_yakala(d, k); d.quit()
                if link:
                    df, durum = pdf_analiz_et(link)
                    if df is not None:
                        st.session_state.ozet_df = df
                        st.success(f"✅ {k} Analiz Edildi.")
                    else: st.error(f"❌ {k} Hata: {durum}")
                else: st.error(f"❌ {k} Hata: {mesaj}")

    elif mod == "📋 Virgülle Çoklu":
        liste = st.text_area("Kodları virgülle ayırın (TTE, MAC, ICZ):")
        if st.button("Çoklu Tarama Başlat"):
            kodlar = [i.strip().upper() for i in liste.split(",") if i.strip()]
            d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_ayarlarini_getir())
            for k in kodlar:
                link, mesaj = fintables_link_yakala(d, k)
                if link:
                    df, durum = pdf_analiz_et(link)
                    if df is not None:
                        v = json_oku(); v[k] = {str(date.today()): df.to_dict(orient="records")}
                        with open("fon_gecmisi.json", "w", encoding="utf-8") as f: json.dump(v, f, ensure_ascii=False)
                        st.success(f"✅ {k} kaydedildi.")
                    else: st.warning(f"⚠️ {k} atlandı. Sebep: {durum}")
                else: st.warning(f"⚠️ {k} atlandı. Sebep: {mesaj}")
            d.quit(); st.info("İşlem bitti.")

    elif mod == "🚀 Excel'den Toplu Tarama":
        varsayilan_yol = r"C:\İşler\Deneme\Phyton\Fon\Takasbank TEFAS  Fon Karşılaştırma.xlsx"
        yol = st.text_input("Excel Dosya Yolu:", value=varsayilan_yol)
        
        c1, c2 = st.columns(2)
        if c1.button("1. Excel'den Listeyi Oku"):
            kodlar, mesaj = excel_fon_listesi_cek(yol)
            if kodlar:
                st.session_state.bulunan_fonlar = kodlar
                st.success(f"Excel'den {len(kodlar)} adet fon kodu okundu.")
            else: st.error(mesaj)
            
        if st.session_state.bulunan_fonlar:
            secili = c2.multiselect("Taranacakları Seçin:", st.session_state.bulunan_fonlar, default=st.session_state.bulunan_fonlar)
            if st.button("2. Seçili Fonları Otomatik Tara"):
                d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_ayarlarini_getir())
                bar = st.progress(0)
                durum_kutusu = st.empty(); bilgi_kutusu = st.empty(); log_metni = ""
                
                for i, k in enumerate(secili):
                    durum_kutusu.info(f"🔄 Şuan işlenen fon: **{k}** ({i+1}/{len(secili)})")
                    link, mesaj = fintables_link_yakala(d, k)
                    if link:
                        df, durum = pdf_analiz_et(link)
                        if df is not None:
                            v = json_oku(); v[k] = {str(date.today()): df.to_dict(orient="records")}
                            with open("fon_gecmisi.json", "w", encoding="utf-8") as f: json.dump(v, f, ensure_ascii=False)
                            log_metni = f"✅ {k} kaydedildi.\n" + log_metni
                        else:
                            log_metni = f"⚠️ {k} Atlandı -> {durum}\n" + log_metni
                    else:
                        log_metni = f"⚠️ {k} Atlandı -> {mesaj}\n" + log_metni
                        
                    bilgi_kutusu.code(log_metni)
                    bar.progress((i+1)/len(secili))
                    
                durum_kutusu.success("🎉 Tüm liste tarandı ve işlem tamamlandı!")
                d.quit(); st.balloons()

    if st.session_state.ozet_df is not None:
        st.divider()
        st.dataframe(st.session_state.ozet_df, use_container_width=True, hide_index=True, height=tablo_yuksekligi_hesapla(st.session_state.ozet_df), column_config=kolon_yapisi)

# ------------------------------------------
# SEKME 2: KAYITLI PORTFÖYLER
# ------------------------------------------
with tab2:
    v = json_oku()
    if v:
        f = st.selectbox("Fon Seçin:", sorted(v.keys()))
        t = st.selectbox("Tarih Seçin:", sorted(v[f].keys(), reverse=True))
        df_kayit = pd.DataFrame(v[f][t])
        st.dataframe(df_kayit, use_container_width=True, hide_index=True, height=tablo_yuksekligi_hesapla(df_kayit), column_config=kolon_yapisi)

# ------------------------------------------
# SEKME 3: KARŞILAŞTIRMA
# ------------------------------------------
with tab3:
    v = json_oku()
    if len(v) > 1:
        c1, c2 = st.columns(2)
        f1, f2 = c1.selectbox("1. Fon:", sorted(v.keys())), c2.selectbox("2. Fon:", sorted(v.keys()))
        t1, t2 = c1.selectbox("Tarih (1):", sorted(v[f1].keys())), c2.selectbox("Tarih (2):", sorted(v[f2].keys()))
        if st.button("Karşılaştır 🚀"):
            df1, df2 = pd.DataFrame(v[f1][t1]), pd.DataFrame(v[f2][t2])
            df1 = df1.rename(columns={"Lot": f"Lot_{f1}", "Oran": f"Oran_{f1}"})
            df2 = df2.rename(columns={"Lot": f"Lot_{f2}", "Oran": f"Oran_{f2}"})
            merged = pd.merge(df1, df2, on="Hisse", how="outer").fillna(0)
            st.dataframe(merged, use_container_width=True, hide_index=True, height=tablo_yuksekligi_hesapla(merged))

# ------------------------------------------
# ORTAK VERİ HAZIRLIĞI (SEKME 4 VE 5 İÇİN)
# ------------------------------------------
v = json_oku()
master_df = None
if v:
    havuz_verisi = []
    for fon_kodu, tarihler_dict in v.items():
        if not tarihler_dict: continue
        en_guncel_tarih = sorted(tarihler_dict.keys(), reverse=True)[0]
        fon_df = pd.DataFrame(tarihler_dict[en_guncel_tarih])
        for _, satir in fon_df.iterrows():
            if satir["Lot"] > 0: 
                oran_degeri = satir.get("Oran", satir.get("Portföy Oranı (%)", 0.0))
                havuz_verisi.append({
                    "Hisse": satir["Hisse"],
                    "Fon Kodu": fon_kodu,
                    "Lot": satir["Lot"],
                    "Fon İçi Oran (%)": oran_degeri,
                    "Rapor Tarihi": en_guncel_tarih
                })
    if havuz_verisi:
        master_df = pd.DataFrame(havuz_verisi)

# ------------------------------------------
# SEKME 4: PİYASA LİDERLERİ
# ------------------------------------------
with tab4:
    if master_df is None:
        st.info("⚠️ Analiz yapabilmek için önce veritabanına geçerli fon raporları eklemelisiniz.")
    else:
        st.markdown("Veritabanınızdaki tüm fonların harmanlanmış, **Sıfır (0) lotlu verilerden arındırılmış** liderlik tablosu.")
        
        piyasa_cache = piyasa_verisi_oku()
        
        toplu_df = master_df.groupby("Hisse").agg(
            Tutan_Fon_Sayisi=("Fon Kodu", "nunique"),
            Toplam_Lot=("Lot", "sum")
        ).reset_index().sort_values(by="Toplam_Lot", ascending=False)
        
        oranlar = []
        for _, row in toplu_df.iterrows():
            hisse = row["Hisse"]
            fonlardaki_lot = row["Toplam_Lot"]
            sirket_toplam_lot = piyasa_cache.get(hisse, 0)
            
            if sirket_toplam_lot > 0:
                oranlar.append((fonlardaki_lot / sirket_toplam_lot) * 100)
            else:
                oranlar.append(0.0)
                
        toplu_df["Fonların Hakimiyeti (%)"] = oranlar
        
        hisse_kolon_yapisi = {
            "Hisse": st.column_config.TextColumn("Hisse Kodu", width="medium"),
            "Tutan_Fon_Sayisi": st.column_config.NumberColumn("Bulunduğu Fon Sayısı", width="medium"),
            "Toplam_Lot": st.column_config.NumberColumn("Fonlardaki Toplam Lot", width="medium", format="%d"),
            "Fonların Hakimiyeti (%)": st.column_config.NumberColumn("Fonların Hakimiyeti (%)", width="medium", format="%.2f")
        }

        if YF_HAZIR:
            if st.button("🌐 Listesi Görünen Tüm Hisselerin Piyasa Verisini Yahoo'dan Güncelle"):
                with st.spinner("İnternetten lot verileri çekiliyor, bu işlem hisse sayısına göre 1-2 dakika sürebilir..."):
                    bar = st.progress(0)
                    hisseler_liste = toplu_df["Hisse"].tolist()
                    for i, h in enumerate(hisseler_liste):
                        cekilen_lot = yf_toplam_lot_cek(h)
                        if cekilen_lot > 0:
                            piyasa_cache[h] = cekilen_lot
                        bar.progress((i + 1) / len(hisseler_liste))
                    
                    piyasa_verisi_kaydet(piyasa_cache)
                    st.success("Tüm piyasa verileri güncellendi ve hafızaya alındı!")
                    time.sleep(1)
                    st.rerun() 
        else:
            st.error("⚠️ Yahoo Finance kurulu değil! Komut satırına 'pip install yfinance' yazın.")
            
        st.dataframe(toplu_df, use_container_width=True, hide_index=True, height=tablo_yuksekligi_hesapla(toplu_df), column_config=hisse_kolon_yapisi)

# ------------------------------------------
# SEKME 5: NOKTA ATIŞI HİSSE
# ------------------------------------------
with tab5:
    if master_df is None:
        st.info("⚠️ Analiz için fon verisi gerekli.")
    else:
        st.markdown("Seçtiğiniz hissenin **hangi fonlar tarafından, ne ağırlıkta taşındığını** anında görün.")
        piyasa_cache = piyasa_verisi_oku()
        benzersiz_hisseler = sorted(master_df["Hisse"].unique())
        
        secilen_hisse = st.selectbox("Detaylı analiz için hisse seçin:", ["Seçiniz..."] + benzersiz_hisseler)
        
        if secilen_hisse != "Seçiniz...":
            hisse_detay_df = master_df[master_df["Hisse"] == secilen_hisse].sort_values(by="Lot", ascending=False).copy()
            
            toplam_lot_sayisi = hisse_detay_df["Lot"].sum()
            kac_fon_tutuyor = hisse_detay_df["Fon Kodu"].nunique()
            
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            c1.metric(f"🏢 Tutan Fon Sayısı", kac_fon_tutuyor)
            c2.metric(f"💰 Fonlardaki Toplam Lot", f"{toplam_lot_sayisi:,.0f}".replace(",", "."))
            
            sirketin_gercek_lotu = piyasa_cache.get(secilen_hisse, 0)
            
            if sirketin_gercek_lotu > 0:
                hakimiyet = (toplam_lot_sayisi / sirketin_gercek_lotu) * 100
                c3.metric("🌐 Fonların Şirketteki Payı", f"% {hakimiyet:.2f}")
            else:
                c3.metric("🌐 Fonların Şirketteki Payı", "Veri Yok (Güncelleyin)")
                
            if YF_HAZIR:
                with c4:
                    st.write("") 
                    if st.button("🔄 Bu Hisse İçin Piyasa Lotunu Güncelle", use_container_width=True):
                        with st.spinner("Yahoo'dan çekiliyor..."):
                            yeni_lot = yf_toplam_lot_cek(secilen_hisse)
                            if yeni_lot > 0:
                                piyasa_cache[secilen_hisse] = yeni_lot
                                piyasa_verisi_kaydet(piyasa_cache)
                                st.success("Güncellendi!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Yahoo Finance bu hissenin verisini bulamadı.")

            if toplam_lot_sayisi > 0:
                hisse_detay_df["Kendi Havuzumuzdaki Payı (%)"] = (hisse_detay_df["Lot"] / toplam_lot_sayisi) * 100
            else:
                hisse_detay_df["Kendi Havuzumuzdaki Payı (%)"] = 0.0
            
            detay_kolon_yapisi = {
                "Fon Kodu": st.column_config.TextColumn("Sahip Fon", width="medium"),
                "Hisse": st.column_config.TextColumn("Hisse", width="medium"),
                "Lot": st.column_config.NumberColumn("Elindeki Lot", width="medium", format="%d"),
                "Kendi Havuzumuzdaki Payı (%)": st.column_config.NumberColumn("Fon Havuzundaki Payı (%)", width="medium", format="%.2f"),
                "Fon İçi Oran (%)": st.column_config.NumberColumn("Fonun Kendi Ağırlığı (%)", width="medium", format="%.2f"),
                "Rapor Tarihi": st.column_config.TextColumn("Rapor Tarihi", width="medium")
            }
            
            st.divider()
            st.dataframe(hisse_detay_df, use_container_width=True, hide_index=True, height=tablo_yuksekligi_hesapla(hisse_detay_df), column_config=detay_kolon_yapisi)