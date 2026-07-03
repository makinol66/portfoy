import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import os
import io
import json
import time
import requests
import re 
import logging
import plotly.graph_objects as go 
from datetime import datetime, date, timedelta
from tvDatafeed import TvDatafeed, Interval
from isyatirimhisse import fetch_financials

warnings.filterwarnings('ignore')
logging.getLogger('tvDatafeed').setLevel(logging.CRITICAL)

st.set_page_config(page_title="Sezayi Dursun Borsa Radarı", layout="wide")

if 'tek_k' not in st.session_state:
    st.session_state['tek_k'] = True

if 'ozel_tarih' not in st.session_state:
    st.session_state['ozel_tarih'] = date(2023, 9, 7)

st.markdown("""
<style>
    .block-container {
        max-width: 98% !important;
        padding-top: 1rem !important;
        padding-right: 1rem !important;
        padding-left: 1rem !important;
        padding-bottom: 1rem !important;
    }
    ::-webkit-scrollbar { width: 12px; height: 12px; }
    ::-webkit-scrollbar-track { background: #f1f1f1; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    [data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
</style>
""", unsafe_allow_html=True)

def endeksleri_guncelle():
    durum_metni = st.empty()
    ilerleme = st.progress(0)
    
    tv_kodlar = {
        "BIST TÜM": "", "BIST 500": "BIST:XU500", "BIST 100": "BIST:XU100", 
        "BIST 50": "BIST:XU050", "BIST 30": "BIST:XU030",
        "BIST BANKA": "BIST:XBANK", "BIST SINAİ": "BIST:XUSIN",
        "BIST MALİ": "BIST:XUMAL", "BIST HİZMETLER": "BIST:XUHIZ",
        "BIST TEKNOLOJİ": "BIST:XUTEK", "BIST GIDA": "BIST:XGIDA",
        "BIST HOLDİNG": "BIST:XHOLD", "BIST İLETİŞİM": "BIST:XILTM",
        "BIST İNŞAAT": "BIST:XINSA", "BIST MADENCİLİK": "BIST:XMADN",
        "BIST SPOR": "BIST:XSPOR", "BIST TURİZM": "BIST:XTRZM",
        "BIST TİCARET": "BIST:XTCRT", "BIST ULAŞTIRMA": "BIST:XULAS",
        "BIST KATILIM TÜM": "BIST:XKTUM", "BIST KATILIM 100": "BIST:XK100",
        "BIST KATILIM 50": "BIST:XK050", "BIST KATILIM 30": "BIST:XK030",
        "BIST TEMETTÜ": "BIST:XTMTU", "BIST SÜRDÜRÜLEBİLİRLİK": "BIST:XSRD"
    }
    
    mynet_kodlar = {
        "BIST 500": "xu500-bist-500", "BIST 100": "xu100-bist-100", 
        "BIST 50": "xu050-bist-50", "BIST 30": "xu030-bist-30",
        "BIST BANKA": "xbank-bist-banka", "BIST SINAİ": "xusin-bist-sinai",
        "BIST MALİ": "xumal-bist-mali", "BIST HİZMETLER": "xuhiz-bist-hizmetler",
        "BIST TEKNOLOJİ": "xutek-bist-teknoloji", "BIST GIDA": "xgida-bist-gida-icecek",
        "BIST HOLDİNG": "xhold-bist-holding-ve-yatirim", "BIST İLETİŞİM": "xiltm-bist-iletisim",
        "BIST İNŞAAT": "xinsa-bist-insaat", "BIST MADENCİLİK": "xmadn-bist-madencilik",
        "BIST SPOR": "xspor-bist-spor", "BIST TURİZM": "xtrzm-bist-turizm",
        "BIST TİCARET": "xtcrt-bist-ticaret", "BIST ULAŞTIRMA": "xulas-bist-ulastirma",
        "BIST KATILIM TÜM": "xktum-bist-katilim-tum", "BIST KATILIM 100": "xk100-bist-katilim-100",
        "BIST KATILIM 50": "xk050-bist-katilim-50", "BIST KATILIM 30": "xk030-bist-katilim-30",
        "BIST TEMETTÜ": "xtmtu-bist-temettu", "BIST SÜRDÜRÜLEBİLİRLİK": "xsrd-bist-surdurulebilirlik"
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    
    kaydedilecek_veri = {}
    url_tv = "https://scanner.tradingview.com/turkey/scan"
    
    for i, (isim, tv_kod) in enumerate(tv_kodlar.items()):
        durum_metni.info(f"🌐 {isim} listesi güncelleniyor...")
        hisseler = []
        
        try:
            if isim == "BIST TÜM":
                payload = {"columns": ["name"], "filter": [{"left": "type", "operation": "in_range", "right": ["stock", "fund", "dr"]}]}
            else:
                payload = {"columns": ["name"], "filter": [{"left": "type", "operation": "in_range", "right": ["stock", "fund", "dr"]}, {"left": "index", "operation": "in_range", "right": [tv_kod]}]}
                
            cevap = requests.post(url_tv, json=payload, headers=headers, timeout=5)
            if cevap.ok:
                veri = cevap.json()
                hisseler = sorted([f"{item['d'][0]}.IS" for item in veri.get('data', [])])
        except: pass
        
        if not hisseler:
            if "TÜM" in isim:
                try:
                    url_is = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseSelect"
                    cevap_is = requests.get(url_is, headers=headers, timeout=5)
                    veri_is = cevap_is.json()
                    hisseler = sorted([f"{item['kod']}.IS" for item in veri_is['value']])
                except: pass
            else:
                try:
                    m_kod = mynet_kodlar[isim]
                    url_mynet = f"https://finans.mynet.com/borsa/endeks/{m_kod}/endekshisseleri/"
                    cevap_mynet = requests.get(url_mynet, headers=headers, timeout=5)
                    eslesmeler = re.findall(r'/borsa/hisseler/([a-z0-9]+)-[^/]+/', cevap_mynet.text)
                    if eslesmeler:
                        temiz_kodlar = list(set([k.upper() for k in eslesmeler if 4 <= len(k) <= 5]))
                        hisseler = sorted([f"{k}.IS" for k in temiz_kodlar])
                except: pass
                
        kaydedilecek_veri[isim] = hisseler
        ilerleme.progress((i + 1) / len(tv_kodlar))
        time.sleep(0.3)
        
    with open("endeksler.json", "w", encoding="utf-8") as f:
        json.dump(kaydedilecek_veri, f)
        
    durum_metni.success("✅ Tüm listeler başarıyla güncellendi ve güvence altına alındı!")
    time.sleep(2)
    durum_metni.empty()
    ilerleme.empty()

def sektor_carpanlarini_guncelle():
    durum_metni = st.empty()
    durum_metni.info("⏳ Tüm BIST hisselerinin sektörel verileri çekiliyor. Bu işlem 1-2 dakika sürebilir...")
    
    sektor_ceviri = {
        "Technology": "Teknoloji", "Financial Services": "Finans", "Energy": "Enerji",
        "Industrials": "Sanayi", "Consumer Defensive": "Gıda ve Tüketim", "Basic Materials": "Temel Malzeme",
        "Real Estate": "Gayrimenkul", "Utilities": "Altyapı", "Healthcare": "Sağlık",
        "Communication Services": "İletişim", "Consumer Cyclical": "Döngüsel Tüketim"
    }
    
    try:
        with open("endeksler.json", "r", encoding="utf-8") as f:
            endeks_verisi = json.load(f)
            tum_hisseler = endeks_verisi.get("BIST TÜM", [])
            
        if not tum_hisseler:
            durum_metni.error("⚠️ Önce Endeks Listelerini Güncelleyin!")
            return

        sektor_verileri = []
        islem_bari = st.progress(0)
        
        for i, hisse in enumerate(tum_hisseler):
            try:
                tk = yf.Ticker(hisse)
                info = tk.info
                ing_sektor = info.get('sector', 'Bilinmiyor')
                sektor_adi = sektor_ceviri.get(ing_sektor, ing_sektor)
                
                pddd = info.get('priceToBook', None)
                fk = info.get('trailingPE', None)
                
                if sektor_adi != 'Bilinmiyor':
                    sektor_verileri.append({
                        'Sektör': sektor_adi,
                        'PD/DD': pddd,
                        'F/K': fk
                    })
            except: pass
            
            islem_bari.progress((i + 1) / len(tum_hisseler))
            
        df_sektor = pd.DataFrame(sektor_verileri)
        
        df_sektor['PD/DD'] = pd.to_numeric(df_sektor['PD/DD'], errors='coerce')
        df_sektor['F/K'] = pd.to_numeric(df_sektor['F/K'], errors='coerce')
        
        medyan_pd = df_sektor[df_sektor['PD/DD'] > 0].groupby('Sektör')['PD/DD'].median().to_dict()
        medyan_fk = df_sektor[df_sektor['F/K'] > 0].groupby('Sektör')['F/K'].median().to_dict()
        
        kaydedilecek_veri = {"PD/DD": medyan_pd, "F/K": medyan_fk}
        
        with open("sektor_carpanlari.json", "w", encoding="utf-8") as f:
            json.dump(kaydedilecek_veri, f, ensure_ascii=False)
            
        durum_metni.success("✅ Sektör çarpanları başarıyla hesaplandı ve kaydedildi!")
        time.sleep(2)
        durum_metni.empty()
        islem_bari.empty()
        
    except Exception as e:
        durum_metni.error(f"⚠️ Hata: {e}")

def favorileri_getir():
    if os.path.exists("favoriler.json"):
        try:
            with open("favoriler.json", "r", encoding="utf-8") as f:
                veri = json.load(f)
                if isinstance(veri, list): return veri
                return list(veri.keys()) 
        except Exception: return []
    return []

def favorileri_kaydet(liste_sozlugu):
    sirali_liste = dict(sorted(liste_sozlugu.items()))
    with open("favoriler.json", "w", encoding="utf-8") as f:
        json.dump(sirali_liste, f)

def portfoydeki_hisseleri_getir():
    portfoy_hisseleri = set()
    if os.path.exists("portfoy.json"):
        try:
            with open("portfoy.json", "r", encoding="utf-8") as f:
                cuzdanlar = json.load(f)
                for cuzdan_icerik in cuzdanlar.values():
                    if isinstance(cuzdan_icerik, dict):
                        for varlik_kodu in cuzdan_icerik.keys():
                            if varlik_kodu.endswith('.IS'):
                                portfoy_hisseleri.add(varlik_kodu.replace('.IS', ''))
        except Exception: pass
    return list(portfoy_hisseleri)

def sutun_ayarlari_getir():
    if os.path.exists("sutun_ayarlari.json"):
        try:
            with open("sutun_ayarlari.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: return {}
    return {}

def sutun_ayarlari_kaydet():
    ayarlar = {}
    for k, v in st.session_state.items():
        if k.startswith("chk_"):
            ayarlar[k] = v
    with open("sutun_ayarlari.json", "w", encoding="utf-8") as f:
        json.dump(ayarlar, f)

def hesapla_getiri(df_col, gun_veya_tarih):
    try:
        fyt_son = float(df_col.iloc[-1])
        if isinstance(gun_veya_tarih, int):
            if len(df_col) < 2: return None
            hedef_t = (datetime.now() - timedelta(days=gun_veya_tarih)).strftime('%Y-%m-%d')
            eski_fiyatlar = df_col.loc[:hedef_t]
            if not eski_fiyatlar.empty:
                fyt_eski = float(eski_fiyatlar.iloc[-1]) 
                return round(((fyt_son - fyt_eski) / fyt_eski) * 100, 2)
        else:
            if len(df_col) < 2: return None
            eski_fiyatlar = df_col.loc[gun_veya_tarih.strftime('%Y-%m-%d'):]
            if not eski_fiyatlar.empty:
                fyt_eski = float(eski_fiyatlar.iloc[0])
                return round(((fyt_son - fyt_eski) / fyt_eski) * 100, 2)
    except: pass
    return None

def nadaraya_watson(series, h=8):
    y = series.values
    size = min(len(series), 400) 
    y_cut = y[-size:]
    x_cut = np.arange(size)
    diff = x_cut[:, None] - x_cut[None, :]
    weights = np.exp(-(diff**2) / (2 * h**2))
    nwe_cut = (weights @ y_cut) / np.sum(weights, axis=1)
    result = np.full(len(series), np.nan)
    result[-size:] = nwe_cut
    return pd.Series(result, index=series.index)

def analiz_motoru(hisseler, macd_aktif, hacim_aktif, ema200_aktif, ichi_aktif, nwe_aktif, temel_aktif, teknik_aktif, zirve_aktif, fibo_p, secilen_t, veri_kaynagi):
    baslangic_zamani = time.time() 
    durum_metni = st.empty()
    ilerleme = st.progress(0)
    sonuclar = []
    toplam_hisse = len(hisseler)
    
    sektor_ceviri = {
        "Technology": "Teknoloji", "Financial Services": "Finans", "Energy": "Enerji",
        "Industrials": "Sanayi", "Consumer Defensive": "Gıda ve Tüketim", "Basic Materials": "Temel Malzeme",
        "Real Estate": "Gayrimenkul", "Utilities": "Altyapı", "Healthcare": "Sağlık",
        "Communication Services": "İletişim", "Consumer Cyclical": "Döngüsel Tüketim"
    }
    
    usd_kur = 32.0  
    eur_kur = 35.0  
    usd_hist = pd.Series(dtype=float)
    eur_hist = pd.Series(dtype=float)
    
    if temel_aktif:
        durum_metni.info("⏳ Güncel ve geçmiş döviz kurları kontrol ediliyor...")
        try:
            usd_df = yf.download("TRY=X", period="5y", progress=False)
            if not usd_df.empty: 
                usd_hist = usd_df['Close'].squeeze()
                usd_kur = float(usd_hist.iloc[-1])
                
            eur_df = yf.download("EURTRY=X", period="5y", progress=False)
            if not eur_df.empty: 
                eur_hist = eur_df['Close'].squeeze()
                eur_kur = float(eur_hist.iloc[-1])
        except: pass

    tv = None

    if veri_kaynagi == "Yfinance (Hızlı)":
        period_str = "max" if zirve_aktif else "10y"
        durum_metni.info(f"🚀 {toplam_hisse} varlığın fiyat geçmişi Yfinance ile TEK SEFERDE indiriliyor...")
        try:
            if toplam_hisse > 1:
                toplu_veri = yf.download(hisseler, period=period_str, interval="1d", auto_adjust=True, threads=True, progress=False)
            else:
                toplu_veri = yf.download(hisseler[0], period=period_str, interval="1d", auto_adjust=True, progress=False)
            durum_metni.info("✅ Yfinance fiyatları başarıyla indirildi! Formüller ve skorlar hesaplanıyor...")
        except Exception as e:
            st.error(f"⚠️ Yfinance fiyatları çekilirken hata oluştu: {e}")
            return []
    else:
        durum_metni.info("🚀 Veri motoru başlatılıyor (tvDatafeed)...")
        try:
            tv = TvDatafeed()
            durum_metni.info("✅ TradingView bağlantısı başarılı! Veriler sırayla çekiliyor...")
        except Exception as e:
            st.error(f"⚠️ TradingView bağlantısı kurulamadı: {e}")
            return []

    for i, hisse in enumerate(hisseler):
        if temel_aktif:
            if veri_kaynagi == "tvDatafeed (Hassas)":
                time.sleep(0.2)
            if i > 0 and i % 50 == 0:
                durum_metni.warning(f"🛡️ API engeline takılmamak için 10 saniye mola veriliyor... ({i}/{toplam_hisse})")
                time.sleep(10)
            durum_metni.info(f"🏢 Bilanço ve analiz verileri çekiliyor: {hisse} ({i+1}/{toplam_hisse})")
        else:
            if i % 10 == 0:
                durum_metni.info(f"⚡ {veri_kaynagi} ile formüller işleniyor... ({i+1}/{toplam_hisse})")
        
        try:
            close = pd.Series(dtype=float)
            high = pd.Series(dtype=float)
            low = pd.Series(dtype=float)
            hacim_data = pd.Series(dtype=float)

            if veri_kaynagi == "Yfinance (Hızlı)":
                if toplam_hisse > 1:
                    close = toplu_veri['Close'][hisse].squeeze().dropna()
                    try: high = toplu_veri['High'][hisse].squeeze().dropna()
                    except: pass
                    try: low = toplu_veri['Low'][hisse].squeeze().dropna()
                    except: pass
                    try: hacim_data = toplu_veri['Volume'][hisse].squeeze().dropna()
                    except: pass
                else:
                    close = toplu_veri['Close'].squeeze().dropna()
                    try: high = toplu_veri['High'].squeeze().dropna()
                    except: pass
                    try: low = toplu_veri['Low'].squeeze().dropna()
                    except: pass
                    try: hacim_data = toplu_veri['Volume'].squeeze().dropna()
                    except: pass
                
                if close.empty or len(close) < 3: 
                    hisse_kodu = hisse.replace('.IS', '')
                    endeks_listesi = ["XUTUM", "XU500", "XU100", "XU050", "XU030", "XBANK", "XUSIN", "XUMAL", "XUHIZ", "XUTEK", "XGIDA", "XHOLD", "XILTM", "XINSA", "XMADN", "XSPOR", "XTRZM", "XTCRT", "XULAS", "XKTUM", "XK100", "XK050", "XK030", "XTMTU", "XSRD"]
                    
                    if hisse_kodu in endeks_listesi:
                        try:
                            if tv is None:
                                tv = TvDatafeed() 
                            n_bars_tv = 4000 if zirve_aktif else 2500
                            tv_data = tv.get_hist(symbol=hisse_kodu, exchange='BIST', interval=Interval.in_daily, n_bars=n_bars_tv)
                            if tv_data is not None and not tv_data.empty:
                                close = tv_data['close'].squeeze()
                                high = tv_data['high'].squeeze()
                                low = tv_data['low'].squeeze()
                                hacim_data = tv_data['volume'].squeeze()
                            else:
                                continue
                        except Exception:
                            continue 
                    else:
                        continue

            else:
                time.sleep(0.2)
                hisse_kodu = hisse.replace('.IS', '')
                n_bars_tv = 4000 if zirve_aktif else 2500
                tv_data = tv.get_hist(symbol=hisse_kodu, exchange='BIST', interval=Interval.in_daily, n_bars=n_bars_tv)
                
                if tv_data is not None and not tv_data.empty:
                    close = tv_data['close'].squeeze()
                    high = tv_data['high'].squeeze()
                    low = tv_data['low'].squeeze()
                    hacim_data = tv_data['volume'].squeeze()
                else:
                    continue
            
            if high.empty or len(high) < len(close) * 0.5: high = close.copy()
            if low.empty or len(low) < len(close) * 0.5: low = close.copy()
            if hacim_data.empty: hacim_data = pd.Series(0.0, index=close.index)

            close.index = close.index.tz_localize(None)
            high.index = high.index.tz_localize(None)
            low.index = low.index.tz_localize(None)
            hacim_data.index = hacim_data.index.tz_localize(None)
            
            # --- BÖLÜNME/ANOMALİ TEMİZLİĞİ ---
            gunluk_getiri = close.pct_change()
            anomaliler = gunluk_getiri[(gunluk_getiri < -0.30) | (gunluk_getiri > 0.50)]
            
            if not anomaliler.empty:
                son_anomali_tarihi = anomaliler.index[-1]
                close = close.loc[son_anomali_tarihi + pd.Timedelta(days=1):]
                high = high.loc[son_anomali_tarihi + pd.Timedelta(days=1):]
                low = low.loc[son_anomali_tarihi + pd.Timedelta(days=1):]
                hacim_data = hacim_data.loc[son_anomali_tarihi + pd.Timedelta(days=1):]
                
            if len(close) < 3: continue 

            fyt = float(close.iloc[-1])
            fyt_eski = float(close.iloc[-2]) 
            gunluk_yuzde = ((fyt - fyt_eski) / fyt_eski) * 100 
            
            _zirve_gun = 0
            _zirve_yuzde = 0.0
            if zirve_aktif:
                _max_val = float(close.max())
                _max_date = close.idxmax()
                if pd.notna(_max_date):
                    _zirve_gun = max(0, (pd.Timestamp.today().normalize() - pd.to_datetime(_max_date).normalize()).days)
                _zirve_yuzde = ((_max_val - fyt) / fyt) * 100 if fyt > 0 else 0.0

            gun_sayisi = len(close)
            
            e9 = close.ewm(span=9, min_periods=1).mean().iloc[-1]
            e21 = close.ewm(span=21, min_periods=1).mean().iloc[-1]
            e50 = close.ewm(span=50, min_periods=1).mean().iloc[-1]
            
            delta = close.diff()
            up = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=1).mean()
            down = -delta.where(delta < 0, 0).ewm(alpha=1/14, min_periods=1).mean()
            rs = up / down
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            if pd.isna(rsi): rsi = 50.0
            
            f_gun = 252 if fibo_p == "1 Yıl" else (756 if fibo_p == "3 Yıl" else 1260)
            f_veriler = close.tail(f_gun)
            f_max, f_min = float(f_veriler.max()), float(f_veriler.min())
            f_fark = f_max - f_min
            
            if gun_sayisi >= 200:
                e200 = close.ewm(span=200).mean().iloc[-1]
                e200_sart = fyt > e200
                e200_txt = "✅ Olumlu" if e200_sart else "❌ Olumsuz"
            else:
                e200 = np.nan
                e200_sart = True 
                e200_txt = "➖ Yeni Varlık"
            e200_onay = e200_sart if ema200_aktif else True

            if f_fark > 0:
                f_lev = [f_max - (f_fark * x) for x in [0.236, 0.382, 0.500, 0.618, 0.786]]
                f_ext = [f_max + (f_fark * x) for x in [0.618, 1.618, 2.618, 3.618, 4.236]] 
                
                if fyt >= f_max: fb = "🚀 Zirve Kırıldı (Uzantı)"
                elif fyt >= f_lev[0]: fb = "🔴 Zirve-%23.6"
                elif fyt >= f_lev[1]: fb = "🔸 %23.6-%38.2"
                elif fyt >= f_lev[2]: fb = "⚡ %38.2-%50.0"
                elif fyt >= f_lev[3]: fb = "⭐ %50.0-%61.8 (Altın)"
                elif fyt >= f_lev[4]: fb = "🔵 %61.8-%78.6"
                else: fb = "⚫ %78.6-Dip"
            else:
                f_lev = []
                f_ext = []
                fb = "➖ Yeni Varlık"

            tum_seviyeler = [e9, e21, e50, f_max, f_min] + f_lev + f_ext
            if pd.notna(e200): tum_seviyeler.append(e200)
            
            tum_seviyeler = sorted(list(set([round(val, 2) for val in tum_seviyeler if pd.notna(val) and val > 0])))
            
            alt_seviyeler = [s for s in tum_seviyeler if s < (fyt * 0.995)]
            ust_seviyeler = [s for s in tum_seviyeler if s > (fyt * 1.005)]
            
            destek = alt_seviyeler[-1] if alt_seviyeler else (fyt * 0.95)
            direnc = ust_seviyeler[0] if ust_seviyeler else (fyt * 1.10)
            
            hedef_pot = ((direnc - fyt) / fyt) * 100
            stop_marji = ((destek - fyt) / fyt) * 100 

            s_hacim = hacim_data.iloc[-1]
            h_ort20 = hacim_data.rolling(20, min_periods=1).mean().iloc[-1]
            
            if h_ort20 > 0:
                h_str = f"{s_hacim/1e6:.1f}M" if s_hacim >= 1e6 else f"{s_hacim/1e3:.1f}B"
                h_yuzde = ((s_hacim - h_ort20)/h_ort20)*100
                if h_yuzde > 50: h_durum = f"🔥 Ç.Yüksek (+%{h_yuzde:.0f})"
                elif h_yuzde > 10: h_durum = f"▲ Yüksek (+%{h_yuzde:.0f})"
                elif h_yuzde < -20: h_durum = f"▼ Düşük (%{h_yuzde:.0f})"
                else: h_durum = "➖ Normal"
                hacim_sart = s_hacim > hacim_data.rolling(10, min_periods=1).mean().iloc[-1]
                h_txt = "✅ Olumlu" if hacim_sart else "❌ Olumsuz"
            else:
                h_str = "➖"
                h_durum = "➖ Hacimsiz"
                h_yuzde = 0.0
                hacim_sart = True
                h_txt = "➖ Muaf"
                
            h_onay = hacim_sart if hacim_aktif else True

            m_c = close.ewm(span=12, min_periods=1).mean() - close.ewm(span=26, min_periods=1).mean()
            m_s = m_c.ewm(span=9, min_periods=1).mean()
            macd_sart = m_c.iloc[-1] > m_s.iloc[-1]
            m_txt = "✅ Olumlu" if macd_sart else "❌ Olumsuz"
            m_onay = macd_sart if macd_aktif else True 
            
            if gun_sayisi >= 52:
                ts = (high.rolling(9, min_periods=1).max() + low.rolling(9, min_periods=1).min()) / 2
                ks = (high.rolling(26, min_periods=1).max() + low.rolling(26, min_periods=1).min()) / 2
                ssa = ((ts + ks) / 2).shift(26).iloc[-1]
                ssb = ((high.rolling(52, min_periods=1).max() + low.rolling(52, min_periods=1).min()) / 2).shift(26).iloc[-1]
                if pd.isna(ssa) or pd.isna(ssb):
                    ichi_sart = True
                    ichi_txt = "➖ Yeni Varlık"
                else:
                    ichi_sart = (fyt > ssa) and (fyt > ssb)
                    ichi_txt = "✅ Olumlu" if ichi_sart else "❌ Olumsuz"
            else:
                ichi_sart = True
                ichi_txt = "➖ Yeni Varlık"
            ichi_onay = ichi_sart if ichi_aktif else True
            
            if gun_sayisi >= 8:
                nwe_series = nadaraya_watson(close)
                nwe_sart = fyt > nwe_series.iloc[-1]
                nwe_txt = "✅ Olumlu" if nwe_sart else "❌ Olumsuz"
            else:
                nwe_sart = True
                nwe_txt = "➖ Yeni Varlık"
            nwe_onay = nwe_sart if nwe_aktif else True
            
            ma20 = close.rolling(20, min_periods=1).mean().iloc[-1]
            std20 = close.rolling(20, min_periods=2).std().iloc[-1]
            if pd.notna(std20) and ma20 > 0:
                bbG = (4 * std20) / ma20
            else:
                bbG = np.nan
            
            teknik_skor = None
            if teknik_aktif:
                gecerli_maks_puan = 100
                ham_skor = 0
                if e9 > e21: ham_skor += min(15, 5 + (((e9 - e21) / e21) * 100) * 2) 
                if fyt > e50: ham_skor += min(10, 3 + (((fyt - e50) / e50) * 100)) 
                
                if gun_sayisi >= 200:
                    if e200_sart: ham_skor += min(10, 3 + (((fyt - e200) / e200) * 100) * 0.5) 
                else: gecerli_maks_puan -= 10 

                if pd.notna(bbG) and bbG < 0.15: 
                    ham_skor += min(15, max(0, ((0.15 - bbG) / 0.15) * 15))
                elif pd.isna(bbG):
                    gecerli_maks_puan -= 15

                if 55 <= rsi <= 70: ham_skor += 15
                elif 40 < rsi < 55: ham_skor += 5 + ((rsi - 40) / 15) * 10
                elif 70 < rsi <= 85: ham_skor += 5 + ((85 - rsi) / 15) * 10
                    
                if macd_sart: ham_skor += 10
                if h_yuzde > 0: ham_skor += min(10, h_yuzde / 5) 

                if gun_sayisi >= 52:
                    if ichi_sart: ham_skor += 15
                else: gecerli_maks_puan -= 15 

                if gecerli_maks_puan > 0:
                    teknik_skor = int(round((ham_skor / gecerli_maks_puan) * 100))
                    teknik_skor = min(100, max(0, teknik_skor))
                else:
                    teknik_skor = 50

            fk, pddd, roe, sektor_adi = None, None, None, "Endeks/Bilinmiyor"
            pddd_5y_ort = None

            if temel_aktif:
                try:
                    tk = yf.Ticker(hisse)
                    info = tk.info
                    
                    ing_sektor = info.get('sector', 'Endeks/Bilinmiyor')
                    sektor_adi = sektor_ceviri.get(ing_sektor, ing_sektor)
                    
                    fk = info.get('trailingPE', None)
                    fin_para_birimi = info.get('financialCurrency', 'TRY')
                    
                    bv = info.get('bookValue', None)
                    if bv and bv > 0:
                        if fin_para_birimi == 'USD': gercek_bv_tl = bv * usd_kur
                        elif fin_para_birimi == 'EUR': gercek_bv_tl = bv * eur_kur
                        else: gercek_bv_tl = bv
                        pddd = fyt / gercek_bv_tl
                    else: pddd = info.get('priceToBook', None)
                        
                    roe = info.get('returnOnEquity', None)
                    
                    # --- YENİ BÖLÜNME VE DÖVİZ DÜZELTMELİ 5 YILLIK PD/DD HESAPLAMASI ---
                    try:
                        bs = tk.balance_sheet
                        current_shares = info.get('sharesOutstanding', None)
                        
                        if not bs.empty and current_shares is not None and current_shares > 0:
                            bs_idx_lower = [str(i).lower() for i in bs.index]
                            eq_idx = next((i for i, name in enumerate(bs_idx_lower) if "stockholders equity" in name or "total equity" in name), None)
                            
                            if eq_idx is not None:
                                eq_row = bs.iloc[eq_idx]
                                hist_prices_5y = tk.history(period="5y", interval="1mo")
                                
                                pddd_degerleri = []
                                for col_date in bs.columns:
                                    try:
                                        ozkaynak = float(eq_row[col_date])
                                        if pd.isna(ozkaynak) or ozkaynak <= 0: continue
                                        
                                        # 1. Döviz Düzeltmesi (Geçmiş kura göre TL'ye çevirme)
                                        kur_carpani = 1.0
                                        if fin_para_birimi == 'USD' and not usd_hist.empty:
                                            try:
                                                target_dt_kur = pd.to_datetime(col_date).tz_localize(usd_hist.index.tz)
                                                idx_kur = usd_hist.index.get_indexer([target_dt_kur], method='nearest')[0]
                                                kur_carpani = float(usd_hist.iloc[idx_kur])
                                            except: kur_carpani = usd_kur 
                                        elif fin_para_birimi == 'EUR' and not eur_hist.empty:
                                            try:
                                                target_dt_kur = pd.to_datetime(col_date).tz_localize(eur_hist.index.tz)
                                                idx_kur = eur_hist.index.get_indexer([target_dt_kur], method='nearest')[0]
                                                kur_carpani = float(eur_hist.iloc[idx_kur])
                                            except: kur_carpani = eur_kur
                                            
                                        gercek_ozkaynak_tl = ozkaynak * kur_carpani
                                        
                                        # 2. Bölünme Düzeltmesi (Geçmiş Piyasa Değeri Yöntemi)
                                        if hist_prices_5y.index.tz is not None:
                                            target_dt_fiyat = pd.to_datetime(col_date).tz_localize(hist_prices_5y.index.tz)
                                        else:
                                            target_dt_fiyat = pd.to_datetime(col_date).tz_localize(None)
                                            
                                        en_yakin_idx = hist_prices_5y.index.get_indexer([target_dt_fiyat], method='nearest')[0]
                                        fiyat = float(hist_prices_5y.iloc[en_yakin_idx]['Close'])
                                        
                                        # Düzeltilmiş Fiyat * Güncel Hisse = Geçmiş Gerçek Piyasa Değeri
                                        tarihsel_piyasa_degeri = fiyat * current_shares
                                        
                                        if tarihsel_piyasa_degeri > 0 and gercek_ozkaynak_tl > 0:
                                            pddd_degerleri.append(tarihsel_piyasa_degeri / gercek_ozkaynak_tl)
                                    except:
                                        continue
                                        
                                if pddd_degerleri:
                                    pddd_5y_ort = float(np.mean(pddd_degerleri))
                    except Exception:
                        pass
                except: pass

            bbg_onay = True
            if pd.notna(bbG):
                if bbG < 0.12:
                    pass
                else:
                    bbg_onay = False
            
            is_kisa_vade_momentum = (fyt > e9) and (h_yuzde > 15) and (rsi > 60)

            if (e9 > e21) and (fyt > e50) and (55 < rsi < 70) and bbg_onay and m_onay and h_onay and e200_onay and ichi_onay and nwe_onay: 
                if is_kisa_vade_momentum:
                    sinyal = "⚡ GÜÇLÜ AL (Kısa Vade)"
                else:
                    sinyal = "🛡️ GÜÇLÜ AL (Orta Vade)"
            elif (fyt < e50) and (e9 > e21) and (40 < rsi < 55) and m_onay and e200_onay and ichi_onay and nwe_onay: sinyal = "🌱 KADEMELİ"
            elif rsi > 75: sinyal = "⚠️ KÂR AL"
            elif (e9 < e21) and (fyt < e50) and (rsi < 45): sinyal = "⛔ SAT"
            else: sinyal = "⏳ BEKLE"

            satir_verisi = {
                'Hisse': hisse.replace('.IS',''), 
                'Günlük (%)': round(gunluk_yuzde, 2),
                'Fiyat': fyt, 
                'Zirveye Uzaklık (%)': round(_zirve_yuzde, 2) if zirve_aktif else 0.0,
                'Zirve (Gün)': _zirve_gun if zirve_aktif else 0,
                'Destek': round(destek, 2),
                'Direnç': round(direnc, 2),
                'Hedef (%)': round(hedef_pot, 2),
                'Stop (%)': round(stop_marji, 2),
                'Fibonacci': fb, 'Hacim': h_str, 'Hacim Durumu': h_durum,
                'Seçili Tarihten': hesapla_getiri(close, secilen_t),
                '1A': hesapla_getiri(close, 30), '3A': hesapla_getiri(close, 90), '6A': hesapla_getiri(close, 180),
                '1Y': hesapla_getiri(close, 365), '2Y': hesapla_getiri(close, 730), '3Y': hesapla_getiri(close, 1095),
                'TÜM': round(((fyt - float(close.iloc[0])) / float(close.iloc[0])) * 100, 2),
                'EMA 9': round(e9, 2), 'EMA 21': round(e21, 2), 'EMA 50': round(e50, 2), 'EMA 200': round(e200, 2) if not np.isnan(e200) else None, 
                'RSI 14': round(rsi, 2), 'Bollinger (%)': round(bbG * 100, 2) if pd.notna(bbG) else None, 
                'MACD Onay': m_txt, 'Hacim Onay': h_txt, 'EMA 200 Onay': e200_txt, 
                'İçimoku Onay': ichi_txt, 'NWE Onay': nwe_txt
            }
            
            if teknik_aktif: satir_verisi['Teknik Skor'] = teknik_skor
            if temel_aktif:
                satir_verisi['Sektör'] = sektor_adi
                satir_verisi['F/K'] = round(fk, 2) if fk is not None else None
                satir_verisi['PD/DD'] = round(pddd, 2) if pddd is not None else None
                satir_verisi['ROE (%)'] = round(roe * 100, 2) if roe is not None else None
                satir_verisi['Sektör PD/DD'] = None
                
                satir_verisi['5Y Ort. PD/DD'] = round(pddd_5y_ort, 2) if pddd_5y_ort is not None else np.nan
                
                if pddd is not None and pddd_5y_ort is not None and pddd_5y_ort > 0:
                    satir_verisi['PD/DD Sapma (%)'] = round(((pddd - pddd_5y_ort) / pddd_5y_ort) * 100, 2)
                else:
                    satir_verisi['PD/DD Sapma (%)'] = np.nan

            satir_verisi['SİNYAL'] = sinyal
            sonuclar.append(satir_verisi)

        except: pass
        ilerleme.progress((i + 1) / toplam_hisse)
        
    if temel_aktif and sonuclar:
        durum_metni.info("⏳ Sektörel medyanlar önbellekten (JSON) çekiliyor...")
        
        medyan_fk = {}
        medyan_pd = {}
        if os.path.exists("sektor_carpanlari.json"):
            try:
                with open("sektor_carpanlari.json", "r", encoding="utf-8") as f:
                    carpanlar = json.load(f)
                    medyan_fk = carpanlar.get("F/K", {})
                    medyan_pd = carpanlar.get("PD/DD", {})
            except: pass
            
        for s in sonuclar:
            sek = s.get('Sektör', 'Endeks/Bilinmiyor')
            fk_val = s.get('F/K')
            pd_val = s.get('PD/DD')
            roe_val = s.get('ROE (%)')
            
            t_skor = 0
            
            if fk_val is not None and fk_val > 0:
                m_fk = medyan_fk.get(sek, 15) 
                if pd.isna(m_fk) or m_fk is None: m_fk = 15
                if fk_val <= m_fk * 0.8: t_skor += 35
                elif fk_val <= m_fk * 1.2: t_skor += 20
                else: t_skor += 5
                
            if pd_val is not None and pd_val > 0:
                m_pd = medyan_pd.get(sek, 3) 
                if pd.isna(m_pd) or m_pd is None: m_pd = 3
                if pd_val <= m_pd * 0.8: t_skor += 30
                elif pd_val <= m_pd * 1.2: t_skor += 15
                else: t_skor += 5
                s['Sektör PD/DD'] = round(m_pd, 2)
            else:
                s['Sektör PD/DD'] = np.nan
                
            if roe_val is not None:
                if roe_val > 40: t_skor += 35
                elif roe_val > 20: t_skor += 20
                elif roe_val > 0: t_skor += 10
                
            s['Temel Skor'] = min(100, t_skor)

    gecen_sure = time.time() - baslangic_zamani
    simdi = datetime.now().strftime("%H:%M")
    durum_metni.success(f"✅ Analiz tamamlandı. ({simdi}) | ⏱️ Süre: {gecen_sure:.1f} saniye")
    return sonuclar

def ema_grup_degisti():
    if "grup_ema" in st.session_state:
        durum = st.session_state.grup_ema
        for c in ["EMA 9", "EMA 21", "EMA 50"]:
            st.session_state[f"chk_{c}"] = durum
        sutun_ayarlari_kaydet()

def getiri_grup_degisti():
    if "grup_getiri" in st.session_state:
        durum = st.session_state.grup_getiri
        for c in ["1A", "3A", "6A", "1Y"]:
            st.session_state[f"chk_{c}"] = durum
        sutun_ayarlari_kaydet()

def tekil_sutun_degisti():
    sutun_ayarlari_kaydet()

def filtreleri_sifirla():
    st.session_state["arama_kutusu"] = ""
    st.session_state["sadece_fav_kutusu"] = False
    st.session_state["sadece_portfoy_kutusu"] = False
    if "sektor_kutusu" in st.session_state: st.session_state["sektor_kutusu"] = []
    if "sinyal_filtre_kutusu" in st.session_state: st.session_state["sinyal_filtre_kutusu"] = []

# ==========================================
# BAŞLIK VE KONTROL PANELİ
# ==========================================
st.title("🚀 Sezayi Dursun Borsa Radarı")
st.markdown("---")

ust_sol, ust_orta, ust_sag = st.columns([1.5, 1.5, 1])

with ust_sol:
    st.markdown("### ⚙️ Tarama Havuzu")
    secim = st.multiselect(
        "Lütfen havuz(lar)ı seçin:",
        (
            "BIST TÜM", "BIST 500", "BIST 100", "BIST 50", "BIST 30", 
            "BIST BANKA", "BIST SINAİ", "BIST MALİ", "BIST HİZMETLER", "BIST TEKNOLOJİ", 
            "BIST GIDA", "BIST HOLDİNG", "BIST İLETİŞİM", "BIST İNŞAAT", "BIST MADENCİLİK", 
            "BIST SPOR", "BIST TURİZM", "BIST TİCARET", "BIST ULAŞTIRMA", 
            "BIST KATILIM TÜM", "BIST KATILIM 100", "BIST KATILIM 50", "BIST KATILIM 30", 
            "BIST TEMETTÜ", "BIST SÜRDÜRÜLEBİLİRLİK", 
            "Portföydekiler", "Favori Hisseler", "Manuel Giriş", "Endekslerin Kendisi (Kıyaslama)"
        ),
        default=["BIST TÜM"]
    )
    
    bist_secimler = [s for s in secim if s not in ["Favori Hisseler", "Manuel Giriş", "Portföydekiler", "Endekslerin Kendisi (Kıyaslama)"]]
    
    if bist_secimler:
        c_btn_sol, c_btn_sag = st.columns(2)
        with c_btn_sol:
            if st.button("🔄 Endeks Listelerini Güncelle", use_container_width=True, help="Listeleri TradingView'den günceller."):
                endeksleri_guncelle()
                st.rerun()
        with c_btn_sag:
            if st.button("🏢 Sektör Çarpanlarını Güncelle", use_container_width=True, help="Tüm BIST şirketlerinin F/K ve PD/DD medyanlarını hesaplayıp önbelleğe kaydeder."):
                sektor_carpanlarini_guncelle()
                st.rerun()
            
        if os.path.exists("endeksler.json"):
            with open("endeksler.json", "r", encoding="utf-8") as f:
                endeks_verisi = json.load(f)
            
            toplam_hisse_set = set()
            for s in bist_secimler:
                toplam_hisse_set.update(endeks_verisi.get(s, []))
            
            if toplam_hisse_set:
                st.caption(f"📌 Seçili endekslerde toplam **{len(toplam_hisse_set)}** farklı hisse.")
            else:
                st.caption("⚠️ Seçili listeler boş. Lütfen güncelleyin.")
        else:
            st.caption("⚠️ Bilgisayarda kayıtlı liste yok. Lütfen güncelleyin.")
            
    if "Manuel Giriş" in secim:
        manuel_hisseler_input = st.text_area("✍️ Kodları Girin (Virgülle):", "", height=80)
        
    st.markdown("### 🗄️ Veritabanı")
    veri_kaynagi = st.radio(
        "Tarama motorunu seçin:",
        ("Yfinance (Hızlı)", "tvDatafeed (Hassas)"),
        horizontal=True
    )

with ust_orta:
    st.markdown("### 📅 Analiz Ayarları")
    secilen_tarih = st.date_input("Özel Tarih Getirisi Başlangıcı:", st.session_state['ozel_tarih'])
    st.session_state['ozel_tarih'] = secilen_tarih
    secilen_fibo_periyot = st.selectbox("Tablo Fibonacci Periyodu:", ("1 Yıl", "3 Yıl", "5 Yıl"))
    st.markdown("<br>", unsafe_allow_html=True)
    
    cb1, cb2 = st.columns(2)
    if cb1.button("✅ Tümünü Seç", use_container_width=True):
        for k in ['macd_k', 'ema_k', 'hacim_k', 'ichi_k', 'nwe_k', 'temel_k', 'tek_k', 'zirve_k']: 
            st.session_state[k] = True
    if cb2.button("❌ Tümünü Kaldır", use_container_width=True):
        for k in ['macd_k', 'ema_k', 'hacim_k', 'ichi_k', 'nwe_k', 'temel_k', 'tek_k', 'zirve_k']: 
            st.session_state[k] = False

    col_kriter1, col_kriter2 = st.columns(2)
    with col_kriter1:
        macd_istiyor_mu = st.checkbox("📈 MACD Onayı Zorunlu", key='macd_k')
        ema200_istiyor_mu = st.checkbox("📉 EMA200 Üzeri Zorunlu", key='ema_k')
        teknik_istiyor_mu = st.checkbox("🎯 Teknik Skorlama (İsteğe Bağlı)", key='tek_k') 
        temel_istiyor_mu = st.checkbox("🏢 Temel Skor (Bilanço - Yavaş)", key='temel_k') 
    with col_kriter2:
        hacim_istiyor_mu = st.checkbox("📊 Hacim Onayı Zorunlu", key='hacim_k')
        ichimoku_istiyor_mu = st.checkbox("☁️ İçimoku Bulutu Zorunlu", key='ichi_k')
        nwe_istiyor_mu = st.checkbox("🌊 NWE (Nadaraya) Zorunlu", key='nwe_k')
        zirve_istiyor_mu = st.checkbox("🏔️ Zirveye Uzaklık (ATH) Hesapla", key='zirve_k')

with ust_sag:
    st.markdown("### 🗂️ Kısayollar")
    st.markdown("[📊 Temel Analiz (Bilanço & Temettü)](Temel_Analiz)")
    st.markdown("[⭐ Favori Hisseler](Favori_Hisseler)")
    st.markdown("[💼 Portföy Cüzdanım](Portfoy)")
    st.markdown('<a href="/" target="_blank">🔄 Yeni Tarama (Yeni Sekme)</a>', unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    analiz_baslat = st.button("🚀 Piyasayı Analiz Et", type="primary", use_container_width=True)

    if analiz_baslat:
        st.session_state["analiz_sayaci"] = st.session_state.get("analiz_sayaci", 0) + 1

st.markdown("---")

# ==========================================
# GİZLENEBİLİR BİLGİ PANOSU (GENİŞLETİLMİŞ REHBER)
# ==========================================
expander_baslik = "ℹ️ Tarama Kriterleri ve Rehber (Tıklayın)" + ("\u200B" * st.session_state.get("analiz_sayaci", 0))

with st.expander(expander_baslik, expanded=False):
    st.markdown("""
    ### 🎯 Dinamik Hedef ve Stop Seviyeleri (Fibonacci Uzantıları)
    Program, klasik ve sabit destek/direnç noktaları yerine algoritma tabanlı dinamik seviyeler kullanır. Fiyatın geçmiş hareketlerindeki zirve ve dip noktaları tespit edilerek **en yakın Direnç (Hedef)** ve **en yakın Destek (Stop Loss)** otomatik hesaplanır. 
    Özellikle tarihi zirvesini kırmış ve önünde direnç kalmamış hisseler için **Fibonacci Uzantıları (1.618, 2.618 vb.)** devreye girer ve "fiyat nereye kadar gidebilir?" sorusuna matematiksel bir hedef çizer.
    * Tablodaki `Hedef (%)` hissenin önündeki ilk güçlü dirence veya uzantı seviyesine olan uzaklığını belirtir.
    * `Stop (%)` ise olası bir düşüşte fiyatı tutması beklenen ilk güçlü desteğin mesafesidir. İşleme girerken risk yönetimi için kritik bir veridir.

    ---
    ### 📏 Fibonacci Geri Çekilme Seviyeleri (Düzeltme Nerede Biter?)
    Bir hisse yükseliş trendinden sonra düşüşe geçtiğinde (düzeltme), yatırımcıların psikolojik olarak alıma geçtikleri belirli oranlar vardır.
    * **🚀 Zirve Kırıldı (Uzantı):** Hisse tüm zamanların en yüksek seviyesini geçmiş, yeni hedeflere (keşif moduna) yelken açmış durumdadır.
    * **🔴 Zirve-%23.6:** Hisse zirveden çok az düşmüştür. Trend contradicts veya çok güçlüdür, alıcılar fiyatın daha fazla düşmesine izin vermiyordur.
    * **🔸 %23.6-%38.2:** Sağlıklı bir kâr satışı (düzeltme) bölgesidir. Trendin gücünü koruduğu ve yoluna devam etmek için güç topladığı yerdir.
    * **⚡ %38.2-%50.0:** Düzeltmenin biraz derinleştiği ama ana yükseliş beklentisinin bozulmadığı, destek arayışının sürdüğü alandır.
    * **⭐ %50.0-%61.8 (Altın Oran):** Teknik analizde "Altın Oran" olarak bilinir. Orta ve uzun vadeli yatırımcıların pusuya yattığı, maliyetlenmek için en ideal ve en güçlü dönüş (tepki) noktasıdır.
    * **🔵 %61.8-%78.6:** Hisse çok derin bir değer kaybı yaşamıştır. Dip çalışması ve toparlanma süreci uzun sürebilir.
    * **⚫ %78.6-Dip:** Yükseliş trendi tamamen bozulmuş, hisse başladığı noktaya geri dönmüş ağır bir çöküş bölgesidir.

    ---
    ### 🧮 Skorlama ve Teknik Göstergeler (Algoritma Neye Bakar?)
    * **🎯 Teknik Puan (0-100):** Hissenin; Hareketli Ortalamalar (EMA), RSI, MACD, Hacim, İçimoku Bulutu, Nadaraya-Watson ve Bollinger Bantları gibi 7 farklı parametreden aldığı notların ağırlıklı ortalamasıdır. 70 ve üzeri puanlar teknik yapının kusursuza yakın olduğunu gösterir.
    * **🏢 Temel Kalite (0-100):** Hissenin F/K (Fiyat/Kazanç), PD/DD (Piyasa Değeri/Defter Değeri) ve ROE (Özkaynak Kârlılığı) verilerinin **sadece kendi sektöründeki rakipleriyle (sektör medyanı)** adil bir şekilde kıyaslanmasıyla bulunur. 70 üzeri puan, şirketin sektörüne göre hem ucuz hem de oldukça kârlı olduğunu vurgular.
    * **📈 EMA (Üstel Hareketli Ortalamalar):** Fiyatın yakın geçmişteki eğilimini gösterir. Kısa vadelilerin (EMA 9 ve 21), uzun vadelileri (EMA 50 ve 200) yukarı kesmesi (Golden Cross) ve fiyatın bu ortalamaların üstünde tutunması en güvenilir yükseliş sinyallerindendir.
    * **📊 Hacim:** Fiyat hareketinin yakıtıdır. Yükselişin hacimle (son 20 günün ortalamasının üzerine çıkarak) desteklenmesi, kurumsal alıcıların (akıllı paranın) tahtaya girdiğini onaylar.
    * **☁️ İçimoku Bulutu:** Japon teknik analiz aracıdır. Fiyatın bulutun (Senkou A ve B) üzerinde olması, kalın bir destek katmanının üzerinde güvenle, orta/uzun vadeli güçlü bir trendde ilerlediğini müjdeler.
    * **🌊 NWE (Nadaraya-Watson Envelope):** Fiyatlardaki "gürültüyü" yapay zeka ile filtreleyerek asıl yönü çizen, makine öğrenmesi destekli bir eğridir.
    * **📈 MACD:** Trendin gücünü ve dönüş noktalarını yakalar. "Olumlu" olması, alış baskısının satış baskısını yenmeye başladığını teyit eder.
    * **📉 Bollinger Bantları:** Hissenin volatilitesini (oynaklığını) ölçer. Bantların iyice daralması (Squeeze), hissenin enerji biriktirdiğini ve yakında sert bir yöne (tercihen yukarı) patlama yapabileceğini gösterir.

    ---
    ### 📌 Sinyal Durumları (Radar Karar Mekanizması)
    Sistem tüm bu karmaşık verileri süzerek karşınıza net ve anlaşılır 6 farklı aksiyon sinyali çıkarır:
    * **⚡ GÜÇLÜ AL (Kısa Vade / Momentum):** Seçilen tüm teknik onaylar (EMA, MACD, İçimoku vb.) kusursuz şekilde sağlanmıştır. Üstelik hacimde ciddi bir patlama yaşanmış (>%15) ve RSI hızlı bir ivme bandına (60+) girmiştir. Hisse anlık olarak roketlemeye hazırdır, kısa vadeli (vur-kaç veya swing trade) hızlı işlemler için idealdir.
    * **🛡️ GÜÇLÜ AL (Orta/Uzun Vade):** Seçilen tüm teknik temel onaylar alınmıştır (Trend pozitiftir). Ancak fiyat hareketi agresif değildir, hacim daha stabil ve RSI aşırı ısınmamıştır. Trendine oturmuş, emin adımlarla ve daha sakin ilerleyen, uzun soluklu taşımaya uygun hisseleri temsil eder.
    * **🌱 KADEMELİ:** Fiyat çok düşmüş ve henüz kalın EMA50 direncinin altındadır, yani ana düşüş trendi tam bitmemiştir. Ancak dipten dönüş başlamış, kısa vadeli ortalamalar (EMA9 > EMA21) "al" vermiş ve MACD toparlanmıştır. Ucuzdan, dibi yakalayarak yavaş yavaş "kademeli" toplanabilecek bölgedir.
    * **⏳ BEKLE:** Ortalamalar yataya bağlamış, birbirine girmiş ve net bir yön tayini yoktur. Kararsız ve testere piyasasıdır. İşlem yapmak zaman veya para kaybı riski taşır, yönün netleşmesi beklenmelidir.
    * **⚠️ KÂR AL:** Hisse çok kısa sürede aşırı prim yapmış ve teknik göstergeleri (RSI > 75) iyice şişmiştir. Trend hala yukarı olsa da her an sert bir kâr satışı (düzeltme) yiyebilir. Pozisyon küçültmek veya stopları yukarı taşımak için uyarı bölgesidir.
    * **⛔ SAT:** Hem kısa hem orta vadeli trend kırılmış, hareketli ortalamalar aşağı kesmiş ve RSI (45 altı) satış baskısının arttığını onaylamıştır. Düşüşün derinleşme ihtimali yüksektir.
    """)

# ==========================================
# ÇALIŞTIRMA MANTIĞI VE SIRALAMA
# ==========================================
if analiz_baslat:
    st.session_state["tablo_verisi"] = None
    st.session_state["png_goster"] = False 
    
    for key in list(st.session_state.keys()):
        if key.startswith("chk_") or key.startswith("grup_"):
            del st.session_state[key]
            
    filtreleri_sifirla()
    
    try:
        ham_hisseler_set = set()
        
        if not secim:
            st.warning("⚠️ Lütfen en az bir tarama havuzu seçin!")
            st.stop()

        if "Manuel Giriş" in secim:
            if manuel_hisseler_input.strip():
                ham_hisseler_set.update([x.strip() for x in manuel_hisseler_input.split(",") if x.strip()])
            
        if "Favori Hisseler" in secim:
            favoriler_listesi = favorileri_getir()
            if not favoriler_listesi and len(secim) == 1:
                st.warning("Favori listeniz şu an boş! Lütfen önce favoriler sayfasına giderek hisse ekleyin.")
                st.stop()
            ham_hisseler_set.update(favoriler_listesi)
            
        if "Portföydekiler" in secim:
            portfoy_hisseleri = portfoydeki_hisseleri_getir()
            if not portfoy_hisseleri and len(secim) == 1:
                st.warning("💼 Cüzdanınızda (Portföyünüzde) henüz hiç hisse senedi bulunmuyor!")
                st.stop()
            ham_hisseler_set.update(portfoy_hisseleri)
            
        if "Endekslerin Kendisi (Kıyaslama)" in secim:
            endeks_kodlari = ["XUTUM", "XU500", "XU100", "XU050", "XU030", "XBANK", "XUSIN", "XUMAL", "XUHIZ", "XUTEK", "XGIDA", "XHOLD", "XILTM", "XINSA", "XMADN", "XSPOR", "XTRZM", "XTCRT", "XULAS", "XKTUM", "XK100", "XK050", "XK030", "XTMTU", "XSRD"]
            ham_hisseler_set.update(endeks_kodlari)
            
        bist_secimler = [s for s in secim if s not in ["Favori Hisseler", "Manuel Giriş", "Portföydekiler", "Endekslerin Kendisi (Kıyaslama)"]]
        if bist_secimler:
            if os.path.exists("endeksler.json"):
                with open("endeksler.json", "r", encoding="utf-8") as f:
                    endeks_verisi = json.load(f)
                
                for s in bist_secimler:
                    secili_liste = endeks_verisi.get(s, [])
                    if secili_liste:
                        ham_hisseler_set.update([h.replace('.IS', '') for h in secili_liste])
                    else:
                        st.warning(f"⚠️ {s} listesi boş veya bulunamadı. Lütfen '🔄 Endeks Listelerini Güncelle' butonuna tıklayın.")
            else:
                st.warning("⚠️ 'endeksler.json' dosyası bulunamadı. Lütfen yukarıdaki '🔄 Endeks Listelerini Güncelle' butonuna tıklayarak listeleri indirin.")
                st.stop()
            
        hisseler = []
        for k in list(ham_hisseler_set):
            temiz_k = str(k).strip().upper()
            if temiz_k:
                if not temiz_k.endswith(".IS"):
                    temiz_k += ".IS"
                hisseler.append(temiz_k)
        
        if hisseler:
            res = analiz_motoru(hisseler, macd_istiyor_mu, hacim_istiyor_mu, ema200_istiyor_mu, ichimoku_istiyor_mu, nwe_istiyor_mu, temel_istiyor_mu, teknik_istiyor_mu, zirve_istiyor_mu, secilen_fibo_periyot, secilen_tarih, veri_kaynagi)
            if res: 
                df_res = pd.DataFrame(res)
                
                sinyal_sirasi = {
                    "⚡ GÜÇLÜ AL (Kısa Vade)": 1,
                    "🛡️ GÜÇLÜ AL (Orta Vade)": 2,
                    "🌱 KADEMELİ": 3,
                    "⏳ BEKLE": 4,
                    "⚠️ KÂR AL": 5,
                    "⛔ SAT": 6
                }
                
                df_res['Siralama_Puani'] = df_res['SİNYAL'].map(sinyal_sirasi).fillna(99)
                
                if teknik_istiyor_mu:
                    df_res = df_res.sort_values(by=['Siralama_Puani', 'Teknik Skor'], ascending=[True, False]).drop('Siralama_Puani', axis=1).reset_index(drop=True)
                else:
                    df_res = df_res.sort_values(by=['Siralama_Puani', 'Hisse'], ascending=[True, True]).drop('Siralama_Puani', axis=1).reset_index(drop=True)
                
                st.session_state["tablo_verisi"] = df_res
            else:
                st.warning("⚠️ UYARI: Hiçbir hisse senedi için veri çekilemedi. Lütfen internet bağlantınızı kontrol edin.")
            
    except Exception as e: 
        st.error(f"⚠️ Hata oluştu: {e}")

# ==========================================
# TABLO GÖSTERİMİ VE ETKİLEŞİM
# ==========================================
if "tablo_verisi" in st.session_state and st.session_state["tablo_verisi"] is not None:
    try:
        with open("favoriler.json", "r", encoding="utf-8") as f:
            st.session_state.favoriler = json.load(f)
    except:
        st.session_state.favoriler = {}

    df = st.session_state["tablo_verisi"]
    final_cols = list(df.columns)
    if not macd_istiyor_mu and 'MACD Onay' in final_cols: final_cols.remove('MACD Onay')
    if not hacim_istiyor_mu and 'Hacim Onay' in final_cols: final_cols.remove('Hacim Onay')
    if not ema200_istiyor_mu and 'EMA 200 Onay' in final_cols: final_cols.remove('EMA 200 Onay')
    if not ichimoku_istiyor_mu and 'İçimoku Onay' in final_cols: final_cols.remove('İçimoku Onay') 
    if not nwe_istiyor_mu and 'NWE Onay' in final_cols: final_cols.remove('NWE Onay') 
    
    if not temel_istiyor_mu:
        for c in ['Sektör', 'Temel Skor', 'F/K', 'PD/DD', 'Sektör PD/DD', '5Y Ort. PD/DD', 'PD/DD Sapma (%)', 'ROE (%)']:
            if c in final_cols: final_cols.remove(c)
            
    if not teknik_istiyor_mu and 'Teknik Skor' in final_cols:
        final_cols.remove('Teknik Skor')
        
    if not zirve_istiyor_mu:
        for c in ['Zirveye Uzaklık (%)', 'Zirve (Gün)']:
            if c in final_cols: final_cols.remove(c)

    en_saga_alinacaklar = ['Temel Skor', 'Teknik Skor', 'SİNYAL']
    basa_alinacaklar = ['Hisse', 'Sektör', 'Günlük (%)', 'Fiyat', 'Zirveye Uzaklık (%)', 'Zirve (Gün)', 'Destek', 'Direnç', 'Hedef (%)', 'Stop (%)']
    orta_kisim = [c for c in final_cols if c not in basa_alinacaklar and c not in en_saga_alinacaklar]
    
    yeni_sira = []
    for c in basa_alinacaklar:
        if c in final_cols: yeni_sira.append(c)
    yeni_sira.extend(orta_kisim)
    for c in en_saga_alinacaklar:
        if c in final_cols: yeni_sira.append(c)
        
    final_cols = yeni_sira
    df = df[final_cols]

    kayitli_sutun_ayarlari = sutun_ayarlari_getir()

    for s in df.columns:
        chk_key = f"chk_{s}"
        if chk_key not in st.session_state:
            if chk_key in kayitli_sutun_ayarlari:
                st.session_state[chk_key] = kayitli_sutun_ayarlari[chk_key]
            else:
                st.session_state[chk_key] = False if s in ["Seçili Tarihten", "1.5Y", "2Y", "3Y", "5Y", "TÜM", "EMA 200", "Hacim", "F/K", "PD/DD", "Sektör PD/DD", "5Y Ort. PD/DD", "PD/DD Sapma (%)", "ROE (%)"] else True

    with st.expander("👁️ Sütunları Gizle / Göster Paneli", expanded=False):
        c1, c2, _ = st.columns([2, 2, 4])
        
        ema_grup = [c for c in ["EMA 9", "EMA 21", "EMA 50"] if c in df.columns]
        ema_hepsi_acik = all([st.session_state.get(f"chk_{c}", True) for c in ema_grup]) if ema_grup else False
        
        getiri_grup = [c for c in ["1A", "3A", "6A", "1Y"] if c in df.columns]
        getiri_hepsi_acik = all([st.session_state.get(f"chk_{c}", True) for c in getiri_grup]) if getiri_grup else False
        
        with c1:
            st.toggle("📈 EMA (9, 21, 50) Sütunları", value=ema_hepsi_acik, key="grup_ema", on_change=ema_grup_degisti)
        with c2:
            st.toggle("📅 GETİRİLER (1A-1Y) Sütunları", value=getiri_hepsi_acik, key="grup_getiri", on_change=getiri_grup_degisti)
            
        st.markdown("---")
        
        grid = st.columns(6)
        for i, s in enumerate(df.columns):
            grid[i % 6].checkbox(s, key=f"chk_{s}", on_change=tekil_sutun_degisti)

    sec_cols = [s for s in df.columns if st.session_state.get(f"chk_{s}", True)]

    if sec_cols:
        col_baslik, col_siralama = st.columns([2, 1])
        with col_baslik:
            st.subheader("📊 Analiz Sonuçları (Sıralamayı Yandaki Menüden Yapın)")
        with col_siralama:
            siralama_secimi_radar = st.selectbox(
                "📋 Tabloyu Sırala:",
                ["🎯 Sinyal ve Teknik Puan (Önerilen)", "🔤 A'dan Z'ye (Hisse Adı)", "📈 En Çok Kazandıranlar (Günlük %)", "📉 En Çok Kaybettirenler (Günlük %)", "🚀 Hedef Potansiyeli En Yüksek"],
                index=0
            )

        if temel_istiyor_mu and 'Sektör' in df.columns:
            mevcut_sektorler = sorted([s for s in df['Sektör'].unique() if s != 'Endeks/Bilinmiyor' and pd.notna(s)])
            if mevcut_sektorler:
                secili_sektorler = st.multiselect("🏢 Sektöre Göre Filtrele:", mevcut_sektorler, key="sektor_kutusu")
            else:
                secili_sektorler = []
        else:
            secili_sektorler = []

        col_ara1, col_ara2, col_ara3, col_ara4 = st.columns([2, 2, 2, 1])
        
        with col_ara1:
            ara = st.text_input("🔍 Hisse Ara (Baş harflerini yazın):", key="arama_kutusu").upper()
            
        with col_ara2:
            sinyal_listesi = ["⚡ GÜÇLÜ AL (Kısa Vade)", "🛡️ GÜÇLÜ AL (Orta Vade)", "🌱 KADEMELİ", "⏳ BEKLE", "⚠️ KÂR AL", "⛔ SAT"]
            secili_sinyaller = st.multiselect("🚦 Sinyale Göre Filtrele:", sinyal_listesi, key="sinyal_filtre_kutusu")
            
        with col_ara3:
            st.markdown("<br>", unsafe_allow_html=True) 
            cb_fav, cb_port = st.columns(2)
            with cb_fav:
                sadece_favoriler = st.checkbox("⭐ Sadece Favori", key="sadece_fav_kutusu")
            with cb_port:
                sadece_portfoy = st.checkbox("💼 Sadece Portföy", key="sadece_portfoy_kutusu")
            
        with col_ara4:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("🔄 Sıfırla", on_click=filtreleri_sifirla, use_container_width=True)

        df_f = df.copy()
        
        if ara:
            df_f = df_f[df_f['Hisse'].str.startswith(ara, na=False)]
            
        fav_liste = favorileri_getir()
        if sadece_favoriler:
            df_f = df_f[df_f['Hisse'].isin(fav_liste)]
            
        if sadece_portfoy:
            portfoy_listesi = portfoydeki_hisseleri_getir()
            df_f = df_f[df_f['Hisse'].isin(portfoy_listesi)]
            
        if secili_sektorler:
            df_f = df_f[df_f['Sektör'].isin(secili_sektorler)]
            
        if secili_sinyaller:
            df_f = df_f[df_f['SİNYAL'].isin(secili_sinyaller)]

        if "A'dan Z'ye" in siralama_secimi_radar: df_f = df_f.sort_values(by="Hisse", ascending=True)
        elif "Kazandıranlar" in siralama_secimi_radar: df_f = df_f.sort_values(by="Günlük (%)", ascending=False)
        elif "Kaybettirenler" in siralama_secimi_radar: df_f = df_f.sort_values(by="Günlük (%)", ascending=True)
        elif "Hedef" in siralama_secimi_radar and "Hedef (%)" in df_f.columns: df_f = df_f.sort_values(by="Hedef (%)", ascending=False)

        df_f = df_f.reset_index(drop=True)

        h_calc = (len(df_f) + 1) * 35 + 45
        tablo_h = min(h_calc, 1120)
        
        df_gosterim = df_f[sec_cols].copy()
        df_gosterim.insert(0, "❤️", df_f["Hisse"].apply(lambda x: x in fav_liste))
        df_gosterim.insert(1, "#", range(1, len(df_gosterim) + 1))  
        
        if "Hisse" in df_gosterim.columns:
            df_gosterim["Hisse"] = "https://fintables.com/sirketler/" + df_f["Hisse"]
            v_idx = df_gosterim.columns.get_loc("Hisse")
            df_gosterim.insert(v_idx + 1, "TV", df_f["Hisse"].apply(lambda x: f"https://tr.tradingview.com/chart/RGKAKhX4/?symbol=BIST%3A{x.replace('.IS', '')}"))
        
        col_ayarlari = {
            "❤️": st.column_config.CheckboxColumn("❤️", help="Favorilere Ekle", default=False),
            "#": st.column_config.NumberColumn("#", format="%d", disabled=True),
            "Hisse": st.column_config.LinkColumn("Hisse", display_text=r"https://fintables.com/sirketler/(.*)", disabled=True),
            "TV": st.column_config.LinkColumn("TV", display_text="📈", disabled=True, width=40),
            "Sektör": st.column_config.TextColumn("Sektör", disabled=True), 
            "Fiyat": st.column_config.NumberColumn(format="%.2f"), 
            "Günlük (%)": st.column_config.NumberColumn("Günlük (%)", format="%.2f %%"),
            "Zirveye Uzaklık (%)": st.column_config.NumberColumn("Zirveye Uzaklık (%)", format="%.2f %%"),
            "Zirve (Gün)": st.column_config.NumberColumn("Zirve (Gün)", format="%d"),
            "Destek": st.column_config.NumberColumn("Destek", format="%.2f"),
            "Direnç": st.column_config.NumberColumn("Direnç", format="%.2f"),
            "Hedef (%)": st.column_config.NumberColumn("Hedef (%)", format="%.2f %%"),
            "Stop (%)": st.column_config.NumberColumn("Stop (%)", format="%.2f %%"),
            "RSI 14": st.column_config.NumberColumn(format="%.1f"),
            "EMA 9": st.column_config.NumberColumn(format="%.2f"),
            "EMA 21": st.column_config.NumberColumn(format="%.2f"),
            "EMA 50": st.column_config.NumberColumn(format="%.2f"),
            "EMA 200": st.column_config.NumberColumn(format="%.2f"),
            "Bollinger (%)": st.column_config.NumberColumn(format="%.2f %%")
        }
        
        if "Teknik Skor" in sec_cols:
            df_gosterim["Teknik Skor"] = pd.to_numeric(df_gosterim["Teknik Skor"], errors='coerce').fillna(0)
            col_ayarlari["Teknik Skor"] = st.column_config.ProgressColumn("Teknik Puan", format="%d", min_value=0, max_value=100) 
        
        if "Temel Skor" in sec_cols:
            df_gosterim["Temel Skor"] = pd.to_numeric(df_gosterim["Temel Skor"], errors='coerce').fillna(0)
            col_ayarlari["Temel Skor"] = st.column_config.ProgressColumn("Temel Kalite", format="%d", min_value=0, max_value=100)
        
        for num_col in ["F/K", "PD/DD", "Sektör PD/DD", "5Y Ort. PD/DD", "PD/DD Sapma (%)", "ROE (%)"]:
            if num_col in sec_cols:
                df_gosterim[num_col] = pd.to_numeric(df_gosterim[num_col], errors='coerce')
        
        if "F/K" in sec_cols: col_ayarlari["F/K"] = st.column_config.NumberColumn(format="%.2f")
        if "PD/DD" in sec_cols: col_ayarlari["PD/DD"] = st.column_config.NumberColumn(format="%.2f")
        if "Sektör PD/DD" in sec_cols: col_ayarlari["Sektör PD/DD"] = st.column_config.NumberColumn("Sektör PD/DD", format="%.2f")
        if "5Y Ort. PD/DD" in sec_cols: col_ayarlari["5Y Ort. PD/DD"] = st.column_config.NumberColumn("5Y Ort. PD/DD", format="%.2f")
        if "PD/DD Sapma (%)" in sec_cols: col_ayarlari["PD/DD Sapma (%)"] = st.column_config.NumberColumn("PD/DD Sapma (%)", format="%.2f %%")
        if "ROE (%)" in sec_cols: col_ayarlari["ROE (%)"] = st.column_config.NumberColumn(format="%.2f %%")
        
        edited_df = st.data_editor(df_gosterim, use_container_width=True, height=tablo_h, hide_index=True, disabled=sec_cols + ["#"], column_config=col_ayarlari)
        
        degisim_var = False
        for idx, row in edited_df.iterrows():
            hisse_adi = df_f.loc[idx, "Hisse"] 
            is_fav = row["❤️"]
            
            if is_fav and hisse_adi not in fav_liste:
                st.session_state.favoriler[hisse_adi] = {"takipte": False, "maliyet": 0.0}
                degisim_var = True
            elif not is_fav and hisse_adi in fav_liste:
                if hisse_adi in st.session_state.favoriler:
                    del st.session_state.favoriler[hisse_adi]
                degisim_var = True
                
        if degisim_var:
            favorileri_kaydet(st.session_state.favoriler)
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        c_btn1, c_btn2, c_btn3 = st.columns([2, 2, 6])
        
        with c_btn1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf) as w: df_f[sec_cols].to_excel(w, index=False)
            st.download_button("📥 Excel İndir", buf.getvalue(), f"Radar_{datetime.now().strftime('%d_%m')}.xlsx", type="primary", use_container_width=True)
            
        with c_btn2:
            if st.button("📸 Tabloyu PNG Olarak Çiz", use_container_width=True):
                st.session_state["png_goster"] = True

        if st.session_state.get("png_goster", False):
            df_png = df_gosterim.copy()
            df_png["❤️"] = df_png["❤️"].map({True: "⭐", False: ""})
            
            if "Hisse" in df_png.columns:
                df_png["Hisse"] = df_f["Hisse"]
            
            def formatla(deger, format_tipi, yuzde_mi=False):
                if pd.isna(deger) or deger in ["", "None", "nan", "NaN", None]:
                    return "-"
                try:
                    sayi = float(deger)
                    sonuc = format_tipi.format(sayi)
                    return f"% {sonuc}" if yuzde_mi else sonuc
                except:
                    return str(deger)

            for col in df_png.columns:
                if col == "#":
                    df_png[col] = df_png[col].astype(str)
                elif col in ["Fiyat", "Destek", "Direnç", "F/K", "PD/DD", "Sektör PD/DD", "5Y Ort. PD/DD", "PD/DD Sapma (%)"] or "EMA" in col:
                    df_png[col] = df_png[col].apply(lambda x: formatla(x, "{:.2f}"))
                elif "RSI" in col:
                    df_png[col] = df_png[col].apply(lambda x: formatla(x, "{:.1f}"))
                elif "Günlük" in col or "Hedef" in col or "Stop" in col or "Pot." in col or "Bollinger" in col or "Seçili" in col or ("Zirve" in col and "%" in col) or "1A" in col or "TÜM" in col or "ROE" in col:
                    df_png[col] = df_png[col].apply(lambda x: formatla(x, "{:.2f}", True))
                elif "Zirve (Gün)" in col:
                    df_png[col] = df_png[col].apply(lambda x: formatla(x, "{:.0f}"))
                else:
                    df_png[col] = df_png[col].astype(str).replace(["nan", "None", "<NA>", "NaN"], "-")

            fig = go.Figure(data=[go.Table(
                header=dict(values=list(df_png.columns),
                            fill_color='#2C3E50',
                            font=dict(color='white', size=12, family="Arial"),
                            align='center'),
                cells=dict(values=[df_png[col] for col in df_png.columns],
                           fill_color='#F7F9F9',
                           font=dict(color='#2C3E50', size=11, family="Arial"),
                           align='center'))
            ])
            
            tablo_yuksekligi = max(400, len(df_png) * 35 + 50)
            fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=tablo_yuksekligi)
            
            st.markdown("---")
            col_uyari, col_kapat = st.columns([8, 2])
            with col_uyari:
                st.info("👇 **Resim İndirme:** Aşağıdaki tablonun sağ üst köşesindeki **kamera (📷)** ikonuna tıklayın.")
            with col_kapat:
                if st.button("❌ Önizlemeyi Gizle", use_container_width=True):
                    st.session_state["png_goster"] = False
                    st.rerun()
                    
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# İNTERAKTİF GRAFİK
# ==========================================
if "tablo_verisi" in st.session_state and st.session_state["tablo_verisi"] is not None:
    st.markdown("---")
    st.markdown("### 📈 İnteraktif Hisse Grafiği")
    tablo_h = sorted(st.session_state["tablo_verisi"]['Hisse'].tolist())
    c1, c2 = st.columns(2); s_g = c1.selectbox("📂 Seç:", tablo_h, index=None); y_g = c2.text_input("✍️ Yaz:").upper()
    p = st.radio("⏳ Periyot:", ("1 Ay", "3 Ay", "6 Ay", "1 Yıl", "10 Yıl"), index=3, horizontal=True)
    ciz = y_g if y_g else s_g
    if ciz:
        hs = ciz if ciz.endswith(".IS") else ciz + ".IS"
        gv = yf.download(hs, period={"1 Ay":"1mo","3 Ay":"3mo","6 Ay":"6mo","1 Yıl":"1y","10 Yıl":"10y"}[p], progress=False)
        if not gv.empty:
            kp = gv['Close'].squeeze(); high_p = gv['High'].squeeze(); low_p = gv['Low'].squeeze()
            kp.index = kp.index.tz_localize(None)
            plot_df = pd.DataFrame({"Fiyat": kp})
            fmax, fmin = kp.max(), kp.min(); ff = fmax-fmin
            
            for x in [0.0, 23.6, 38.2, 50.0, 61.8, 78.6, 100.0]: plot_df[f"Fib %{x}"] = fmax - (ff * x / 100)
            for x in [61.8, 161.8]: plot_df[f"Ext %{x}"] = fmax + (ff * x / 100)
            
            secenekler = ["Fiyat", "Fibonacci", "Fib Uzantı", "EMA 9", "EMA 21", "EMA 50", "EMA 200", "İçimoku Bulutu", "Nadaraya-Watson"]
            sel = st.multiselect("Göster:", secenekler, default=["Fiyat", "Fibonacci"]) 
            
            final_p = []
            for s in sel:
                if s == "Fibonacci": 
                    final_p.extend([c for c in plot_df.columns if "Fib %" in c])
                elif s == "Fib Uzantı":
                    final_p.extend([c for c in plot_df.columns if "Ext %" in c])
                elif s == "İçimoku Bulutu":
                    ts = (high_p.rolling(9).max() + low_p.rolling(9).min()) / 2
                    ks = (high_p.rolling(26).max() + low_p.rolling(26).min()) / 2
                    plot_df["Senkou A"] = ((ts + ks) / 2).shift(26)
                    plot_df["Senkou B"] = ((high_p.rolling(52).max() + low_p.rolling(52).min()) / 2).shift(26)
                    final_p.extend(["Senkou A", "Senkou B"])
                elif s == "Nadaraya-Watson":
                    plot_df["NWE"] = nadaraya_watson(kp)
                    final_p.append("NWE")
                elif s != "Fiyat":
                    plot_df[s] = kp.ewm(span=int(s.split()[-1])).mean()
                    final_p.append(s)
            
            if "Fiyat" in sel and "Fiyat" not in final_p: final_p.insert(0, "Fiyat")
            st.line_chart(plot_df[final_p])