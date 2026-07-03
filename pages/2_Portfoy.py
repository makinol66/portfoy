import streamlit as st
import yfinance as yf
import db_sync
import pandas as pd
import os
import json
import warnings
import time
import requests
import re
import numpy as np
import concurrent.futures
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Portföy Cüzdanım", layout="wide")

# ==========================================
# ÖZEL TASARIM (CSS)
# ==========================================
st.markdown("""
<style>
    ::-webkit-scrollbar { width: 12px; }
    ::-webkit-scrollbar-track { background: #f1f1f1; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    
    div[data-testid="metric-container"] {
        background-color: #f7f9f9;
        border: 1px solid #e0e0e0;
        padding: 5% 5% 5% 10%;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# YARDIMCI FONKSİYONLAR & VERİLER
# ==========================================
def tr_format(sayi, kusurat=2):
    if pd.isna(sayi) or sayi is None: return "0,00"
    formatli = f"{float(sayi):,.{kusurat}f}"
    return formatli.replace(",", "X").replace(".", ",").replace("X", ".")

def filtreleri_sifirla():
    if "arama_kutusu" in st.session_state: st.session_state["arama_kutusu"] = ""
    if "ara_mod1" in st.session_state: st.session_state["ara_mod1"] = ""
    if "sadece_fav_kutusu" in st.session_state: st.session_state["sadece_fav_kutusu"] = False
    if "sinyal_filtre_kutusu" in st.session_state: st.session_state["sinyal_filtre_kutusu"] = []

def favorileri_getir():
    veri = db_sync.load_data("favoriler", {})
    if isinstance(veri, dict): return veri
    if isinstance(veri, list): return {k: {"takipte": False, "maliyet": 0.0} for k in veri}
    return {}

def favorileri_kaydet(liste_sozlugu):
    sirali_liste = dict(sorted(liste_sozlugu.items()))
    db_sync.save_data("favoriler", sirali_liste)

# --- SÜTUN GİZLE/GÖSTER (KALICI AYARLAR) ---
def portfoy_sutun_ayarlari_getir():
    if os.path.exists("portfoy_sutun_ayarlari.json"):
        try:
            with open("portfoy_sutun_ayarlari.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: return {}
    return {}

def portfoy_sutun_ayarlari_kaydet():
    ayarlar = {}
    for k, v in st.session_state.items():
        if k.startswith("pchk_"):
            ayarlar[k] = v
    with open("portfoy_sutun_ayarlari.json", "w", encoding="utf-8") as f:
        json.dump(ayarlar, f)

def portfoy_sutun_degisti():
    portfoy_sutun_ayarlari_kaydet()

def zirve_tetikle():
    st.session_state.force_guncelleme = True

# --- CÜZDAN NAKİT/TAKAS FONKSİYONLARI ---
CUZDAN_BAKIYE_DOSYASI = "cuzdan_bakiyeler.json"

def bakiyeler_getir():
    return db_sync.load_data("cuzdan_bakiyeler", {})

def bakiyeler_kaydet(veri):
    db_sync.save_data("cuzdan_bakiyeler", veri)

cuzdan_bakiyeler = bakiyeler_getir()

# --- İŞLEM GEÇMİŞİ FONKSİYONLARI ---
ISLEM_GECMISI_DOSYASI = "islem_gecmisi.json"

def islem_gecmisi_getir():
    return db_sync.load_data("islem_gecmisi", {})

def islem_gecmisi_kaydet(veri):
    db_sync.save_data("islem_gecmisi", veri)

islem_gecmisi = islem_gecmisi_getir()

@st.cache_data(ttl=600)
def bloomberg_fon_verilerini_cek():
    url = "https://www.bloomberght.com/yatirim-fonlari/fon-karsilastirma"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            df_list = pd.read_html(r.text)
            hedef_df = None
            for df in df_list:
                if 'Kod' in df.columns and 'Fiyat' in df.columns:
                    hedef_df = df
                    break
            if hedef_df is not None:
                fon_sozlugu = {}
                for index, row in hedef_df.iterrows():
                    kod = str(row['Kod']).upper().strip()
                    try:
                        guncel_fiyat = float(row['Fiyat'])
                        gunluk_y = float(row['Günlük(%)']) if pd.notna(row['Günlük(%)']) else 0.0
                        onceki_fiyat = guncel_fiyat / (1 + (gunluk_y / 100)) if gunluk_y != 0 else guncel_fiyat
                        fon_sozlugu[kod] = {"guncel": guncel_fiyat, "onceki": onceki_fiyat}
                    except: pass
                return fon_sozlugu
    except: pass
    return {}

def fon_fiyati_getir_canli(fon_kodu):
    url = "https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir"
    headers = {
        "Referer": f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{fon_kodu}",
        "Origin": "https://www.tefas.gov.tr",
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json"
    }
    try:
        # Maksimum tarihi görebilmek için periyodu 60 ay (5 yıl) yapıyoruz
        r = requests.post(url, headers=headers, json={"fonKodu": fon_kodu, "dil": "TR", "periyod": 60}, timeout=3)
        if r.status_code == 200:
            data = r.json()
            if data.get("resultList") and len(data["resultList"]) > 0:
                return float(data["resultList"][-1].get("fiyat", 0.0))
    except: pass
    b_veri = bloomberg_fon_verilerini_cek()
    if fon_kodu in b_veri:
        return float(b_veri[fon_kodu]["guncel"])
    return 0.0

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

VARLIK_CACHE_DOSYASI = "varlik_fiyat_cache.json"

def varlik_cache_getir():
    if os.path.exists(VARLIK_CACHE_DOSYASI):
        try:
            with open(VARLIK_CACHE_DOSYASI, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def varlik_cache_kaydet(veri):
    with open(VARLIK_CACHE_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(veri, f)

# -------------------------------------------------------------
# DİNAMİK PARAMETRELİ SİNYAL VE SKORLAMA FONKSİYONU
# -------------------------------------------------------------
def varlik_fiyatlarini_getir(hisseler, fonlar, sinyal_hesapla=False, force_update=False, 
                             macd_aktif=False, ema200_aktif=False, hacim_aktif=False, 
                             ichi_aktif=False, nwe_aktif=False, teknik_aktif=True, temel_aktif=False, zirve_hesapla=False):
    fiyatlar = varlik_cache_getir()
    guncelleme_yapildi = False
    
    simdi = datetime.now()
    bugun_tarih = simdi.strftime("%Y-%m-%d")

    if force_update:
        hisseler_cekilecek = hisseler
        fonlar_cekilecek = fonlar
        fiyatlar = {"CACHE_DATE": bugun_tarih}
        guncelleme_yapildi = True
    else:
        hisseler_cekilecek = [h for h in hisseler if h not in fiyatlar]
        fonlar_cekilecek = [f for f in fonlar if f not in fiyatlar]

    basarili_hisseler = []

    def hisse_hesapla_ve_ekle(h_kodu, close_s, high_s=None, low_s=None, hacim_s=None, is_adjusted=True):
        if close_s is None or len(close_s) < 1:
            return False

        if len(close_s) >= 2:
            fyt = float(close_s.iloc[-1])
            onceki_fyt = float(close_s.iloc[-2])
            
            # --- ZİRVE HESAPLAMALARI & BÖLÜNME KONTROLÜ ---
            _zirve_gun = 0
            _zirve_yuzde = 0.0
            if zirve_hesapla:
                # BİST'te bir günde %20'den büyük düşüş normal şartlarda olmaz (Taban sınırı).
                # Eğer fiyat dünden bugüne %25'ten fazla düşmüşse (oran < 0.75) bölünmüştür.
                oranlar = close_s / close_s.shift(1)
                bolunme_noktalari = oranlar[oranlar < 0.75]
                
                if not bolunme_noktalari.empty:
                    # En son bölünme gününü bul ve o günden sonrasını baz al
                    son_bolunme_tarihi = bolunme_noktalari.index[-1]
                    close_s_zirve = close_s.loc[son_bolunme_tarihi:]
                else:
                    close_s_zirve = close_s

                _max_val = float(close_s_zirve.max())
                _max_date = close_s_zirve.idxmax()
                
                if pd.notna(_max_date):
                    _zirve_gun = max(0, (pd.Timestamp.today().normalize() - pd.to_datetime(_max_date).normalize()).days)
                _zirve_yuzde = ((_max_val - fyt) / fyt) * 100 if fyt > 0 else 0.0

            fiyat_data = {"guncel": fyt, "onceki": onceki_fyt, "destek": 0.0, "direnc": 0.0, "hedef_pot": 0.0, "stop_marji": 0.0, "sinyal": "➖", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": _zirve_yuzde, "zirve_gun": _zirve_gun}
            
            if sinyal_hesapla and len(close_s) >= 5:
                e9 = close_s.ewm(span=9, min_periods=1).mean().iloc[-1]
                e21 = close_s.ewm(span=21, min_periods=1).mean().iloc[-1]
                e50 = close_s.ewm(span=50, min_periods=1).mean().iloc[-1]
                e200 = close_s.ewm(span=200).mean().iloc[-1] if len(close_s) >= 200 else np.nan
                
                f_max, f_min = float(close_s.max()), float(close_s.min())
                f_fark = f_max - f_min
                
                f_lev, f_ext = [], []
                if f_fark > 0:
                    f_lev = [f_max - (f_fark * x) for x in [0.236, 0.382, 0.500, 0.618, 0.786]]
                    f_ext = [f_max + (f_fark * x) for x in [0.618, 1.618, 2.618, 3.618, 4.236]]
                    
                tum_seviyeler = sorted(list(set([round(val, 2) for val in ([e9, e21, e50, f_max, f_min] + f_lev + f_ext + ([e200] if pd.notna(e200) else [])) if pd.notna(val) and val > 0])))
                
                alt_seviyeler = [s for s in tum_seviyeler if s < (fyt * 0.995)]
                ust_seviyeler = [s for s in tum_seviyeler if s > (fyt * 1.005)]
                destek = alt_seviyeler[-1] if alt_seviyeler else (fyt * 0.95)
                direnc = ust_seviyeler[0] if ust_seviyeler else (fyt * 1.10)
                
                fiyat_data["destek"] = destek; fiyat_data["direnc"] = direnc
                fiyat_data["hedef_pot"] = ((direnc - fyt) / fyt) * 100; fiyat_data["stop_marji"] = ((destek - fyt) / fyt) * 100

                e200_sart = fyt > e200 if pd.notna(e200) else True
                e200_onay = e200_sart if ema200_aktif else True

                delta = close_s.diff(); up = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=1).mean(); down = -delta.where(delta < 0, 0).ewm(alpha=1/14, min_periods=1).mean()
                rs = up / down; rsi = (100 - (100 / (1 + rs))).iloc[-1]; rsi = 50.0 if pd.isna(rsi) else rsi

                m_c = close_s.ewm(span=12, min_periods=1).mean() - close_s.ewm(span=26, min_periods=1).mean()
                m_s = m_c.ewm(span=9, min_periods=1).mean()
                macd_sart = m_c.iloc[-1] > m_s.iloc[-1]
                macd_onay = macd_sart if macd_aktif else True

                hacim_sart = hacim_s.iloc[-1] > hacim_s.rolling(10, min_periods=1).mean().iloc[-1] if hacim_s is not None else True
                hacim_onay = hacim_sart if hacim_aktif else True

                if high_s is not None and low_s is not None and len(close_s) >= 52:
                    ts = (high_s.rolling(9, min_periods=1).max() + low_s.rolling(9, min_periods=1).min()) / 2
                    ks = (high_s.rolling(26, min_periods=1).max() + low_s.rolling(26, min_periods=1).min()) / 2
                    ssa = ((ts + ks) / 2).shift(26).iloc[-1]
                    ssb = ((high_s.rolling(52, min_periods=1).max() + low_s.rolling(52, min_periods=1).min()) / 2).shift(26).iloc[-1]
                    ichi_sart = (fyt > ssa) and (fyt > ssb) if pd.notna(ssa) and pd.notna(ssb) else True
                else: ichi_sart = True
                ichi_onay = ichi_sart if ichi_aktif else True

                nwe_sart = fyt > nadaraya_watson(close_s).iloc[-1] if len(close_s) >= 8 else True
                nwe_onay = nwe_sart if nwe_aktif else True

                ma20 = close_s.rolling(20, min_periods=1).mean().iloc[-1]
                std20 = close_s.rolling(20, min_periods=2).std().iloc[-1]
                bbG = (4 * std20) / ma20 if pd.notna(std20) and ma20 > 0 else np.nan
                bbg_onay = pd.isna(bbG) or bbG < 0.12

                if hacim_s is not None and len(hacim_s) >= 20:
                    s_hacim = float(hacim_s.iloc[-1])
                    h_ort20 = float(hacim_s.rolling(20, min_periods=1).mean().iloc[-1])
                    h_yuzde = ((s_hacim - h_ort20)/h_ort20)*100 if h_ort20 > 0 else 0
                else:
                    h_yuzde = 0

                is_kisa_vade_momentum = (fyt > e9) and (h_yuzde > 15) and (rsi > 60)

                if (e9 > e21) and (fyt > e50) and (55 < rsi < 70) and bbg_onay and macd_onay and hacim_onay and e200_onay and ichi_onay and nwe_onay: 
                    if is_kisa_vade_momentum:
                        sinyal = "⚡ GÜÇLÜ AL (KV)"
                    else:
                        sinyal = "🛡️ GÜÇLÜ AL (OV)"
                elif (fyt < e50) and (e9 > e21) and (40 < rsi < 55) and macd_onay and e200_onay and ichi_onay and nwe_onay: sinyal = "🌱 KADEMELİ"
                elif rsi > 75: sinyal = "⚠️ KÂR AL"
                elif (e9 < e21) and (fyt < e50) and (rsi < 45): sinyal = "⛔ SAT"
                else: sinyal = "⏳ BEKLE"
                
                fiyat_data["sinyal"] = sinyal

                teknik_skor = 0
                if teknik_aktif:
                    gecerli_maks_puan = 100
                    ham_skor = 0
                    if e9 > e21: ham_skor += min(15, 5 + (((e9 - e21) / e21) * 100) * 2) 
                    if fyt > e50: ham_skor += min(10, 3 + (((fyt - e50) / e50) * 100)) 
                    
                    if len(close_s) >= 200:
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

                    if len(close_s) >= 52:
                        if ichi_sart: ham_skor += 15
                    else: gecerli_maks_puan -= 15 

                    if gecerli_maks_puan > 0:
                        teknik_skor = int(round((ham_skor / gecerli_maks_puan) * 100))
                        teknik_skor = min(100, max(0, teknik_skor))
                    else:
                        teknik_skor = 50
                fiyat_data["teknik_skor"] = teknik_skor

                temel_skor = 0
                if temel_aktif:
                    try:
                        tk = yf.Ticker(h_kodu)
                        info = tk.info
                        fk = info.get('trailingPE', 15)
                        pddd = info.get('priceToBook', 3)
                        roe = info.get('returnOnEquity', 0)
                        
                        t_skor = 0
                        if fk is not None and fk > 0:
                            if fk <= 12: t_skor += 35
                            elif fk <= 18: t_skor += 20
                            else: t_skor += 5
                        if pddd is not None and pddd > 0:
                            if pddd <= 2.4: t_skor += 30
                            elif pddd <= 3.6: t_skor += 15
                            else: t_skor += 5
                        if roe is not None:
                            if roe > 0.40: t_skor += 35
                            elif roe > 0.20: t_skor += 20
                            elif roe > 0: t_skor += 10
                            
                        temel_skor = min(100, t_skor)
                    except: pass
                fiyat_data["temel_skor"] = temel_skor

            fiyatlar[h_kodu] = fiyat_data
            basarili_hisseler.append(h_kodu)
            return True
            
        elif len(close_s) == 1:
            fiyatlar[h_kodu] = {"guncel": float(close_s.iloc[-1]), "onceki": float(close_s.iloc[-1]), "destek": 0, "direnc": 0, "hedef_pot": 0, "stop_marji": 0, "sinyal": "⏳ YENİ HİSSE", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": 0.0, "zirve_gun": 0}
            basarili_hisseler.append(h_kodu)
            return True
        return False

    if hisseler_cekilecek:
        try:
            period_str = "max" if zirve_hesapla else ("2y" if sinyal_hesapla else "3mo")
            toplam_hisse = len(hisseler_cekilecek)
            
            if toplam_hisse > 1:
                toplu_veri = yf.download(hisseler_cekilecek, period=period_str, interval="1d", auto_adjust=True, threads=True, progress=False)
            else:
                toplu_veri = yf.download(hisseler_cekilecek[0], period=period_str, interval="1d", auto_adjust=True, progress=False)
                
            for h in hisseler_cekilecek:
                try:
                    if toplam_hisse > 1:
                        if isinstance(toplu_veri.columns, pd.MultiIndex):
                            if 'Close' in toplu_veri and h in toplu_veri['Close'].columns: 
                                close = toplu_veri['Close'][h].dropna()
                                if sinyal_hesapla:
                                    high = toplu_veri['High'][h].dropna()
                                    low = toplu_veri['Low'][h].dropna()
                                    hacim = toplu_veri['Volume'][h].dropna()
                                else: high, low, hacim = None, None, None
                            else: continue
                        else:
                            if 'Close' in toplu_veri:
                                close = toplu_veri['Close'].dropna()
                                if sinyal_hesapla:
                                    high = toplu_veri['High'].dropna()
                                    low = toplu_veri['Low'].dropna()
                                    hacim = toplu_veri['Volume'].dropna()
                                else: high, low, hacim = None, None, None
                            else: continue
                    else:
                        close = toplu_veri['Close'].dropna()
                        if sinyal_hesapla:
                            high = toplu_veri['High'].dropna()
                            low = toplu_veri['Low'].dropna()
                            hacim = toplu_veri['Volume'].dropna()
                        else: high, low, hacim = None, None, None
                        
                    if hisse_hesapla_ve_ekle(h, close, high, low, hacim, is_adjusted=True):
                        guncelleme_yapildi = True
                except: pass
        except: pass

        kalan_hisseler = [h for h in hisseler_cekilecek if h not in basarili_hisseler]
        if kalan_hisseler:
            try:
                from tvDatafeed import TvDatafeed, Interval
                import logging
                logging.getLogger('tvDatafeed').setLevel(logging.CRITICAL)
                tv = TvDatafeed()
                
                def tvdatafeed_hisse_cek(h):
                    try:
                        tv_sembol = h.replace(".IS", "")
                        n_bars = 1500  # Yaklaşık 6 yıllık işlem günü verisi çekiyoruz
                        tv_data = tv.get_hist(symbol=tv_sembol, exchange='BIST', interval=Interval.in_daily, n_bars=n_bars)
                        
                        if tv_data is not None and not tv_data.empty:
                            close = tv_data['close'].dropna()
                            if sinyal_hesapla:
                                high = tv_data['high'].dropna()
                                low = tv_data['low'].dropna()
                                hacim = tv_data['volume'].dropna()
                            else: high, low, hacim = None, None, None
                            return h, close, high, low, hacim
                    except Exception: pass
                    return h, None, None, None, None

                for h in kalan_hisseler:
                    h_res, close, high, low, hacim = tvdatafeed_hisse_cek(h)
                    if close is not None:
                        # TV Datafeed verileri bölünmeye göre düzeltilmediği için is_adjusted=False gönderiyoruz.
                        if hisse_hesapla_ve_ekle(h, close, high, low, hacim, is_adjusted=False):
                            guncelleme_yapildi = True
                    time.sleep(0.1) 
            except ImportError: pass

    if fonlar_cekilecek:
        bloomberg_verisi = bloomberg_fon_verilerini_cek()
        def fon_getir_multi(f):
            tefas_veri = None
            url = "https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir"
            headers = {
                "Referer": f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{f}",
                "Origin": "https://www.tefas.gov.tr",
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json"
            }
            try:
                periyod_ay = 60 if zirve_hesapla else 12
                r = requests.post(url, headers=headers, json={"fonKodu": f, "dil": "TR", "periyod": periyod_ay}, timeout=3)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("resultList") and len(data["resultList"]) > 0:
                        son_kayit = data["resultList"][-1]
                        g_fiyat = float(son_kayit.get("fiyat", 0))
                        o_fiyat = float(data["resultList"][-2].get("fiyat", g_fiyat)) if len(data["resultList"]) > 1 else g_fiyat
                        
                        _z_yuzde = 0.0
                        _z_gun = 0
                        if zirve_hesapla:
                            max_f = 0.0
                            max_t = 0
                            for itm in data["resultList"]:
                                _f = float(itm.get("fiyat", 0))
                                if _f > max_f:
                                    max_f = _f
                                    max_t = itm.get("tarih")
                            
                            _z_yuzde = ((max_f - g_fiyat)/g_fiyat)*100 if g_fiyat > 0 else 0.0
                            if max_t:
                                try:
                                    dt = pd.to_datetime(max_t, unit='ms') if isinstance(max_t, (int, float)) else pd.to_datetime(max_t)
                                    _z_gun = max(0, (pd.Timestamp.today().normalize() - dt.normalize()).days)
                                except: pass

                        if g_fiyat > 0:
                            tefas_veri = {"guncel": g_fiyat, "onceki": o_fiyat, "zirve_uzaklik_yuzde": _z_yuzde, "zirve_gun": _z_gun}
            except: pass
            
            sonuc = tefas_veri if tefas_veri else bloomberg_verisi.get(f, {"guncel": 0.0, "onceki": 0.0})
            sonuc.update({"destek": 0.0, "direnc": 0.0, "hedef_pot": 0.0, "stop_marji": 0.0, "sinyal": "➖ Fon", "teknik_skor": 0, "temel_skor": 0})
            if "zirve_uzaklik_yuzde" not in sonuc:
                sonuc["zirve_uzaklik_yuzde"] = 0.0
                sonuc["zirve_gun"] = 0
                
            return f, sonuc

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for f, sonuc in executor.map(fon_getir_multi, fonlar_cekilecek):
                fiyatlar[f] = sonuc
                guncelleme_yapildi = True

    for h in hisseler_cekilecek:
        if h not in fiyatlar:
            fiyatlar[h] = {"guncel": 0.0, "onceki": 0.0, "destek": 0.0, "direnc": 0.0, "hedef_pot": 0.0, "stop_marji": 0.0, "sinyal": "⚠️ HATA", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": 0.0, "zirve_gun": 0}
            guncelleme_yapildi = True
    for f in fonlar_cekilecek:
        if f not in fiyatlar:
            fiyatlar[f] = {"guncel": 0.0, "onceki": 0.0, "destek": 0.0, "direnc": 0.0, "hedef_pot": 0.0, "stop_marji": 0.0, "sinyal": "⚠️ HATA", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": 0.0, "zirve_gun": 0}
            guncelleme_yapildi = True
            
    if guncelleme_yapildi:
        varlik_cache_kaydet(fiyatlar)

    son_fiyatlar = {}
    for k in hisseler + fonlar:
        son_fiyatlar[k] = fiyatlar.get(k, {"guncel": 0.0, "onceki": 0.0, "destek": 0.0, "direnc": 0.0, "hedef_pot": 0.0, "stop_marji": 0.0, "sinyal": "➖", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": 0.0, "zirve_gun": 0})
        
    return son_fiyatlar

@st.cache_data(ttl=600)
def canli_altin_getir():
    try:
        kur_veri = yf.download(["GC=F", "TRY=X"], period="5d", progress=False)
        ons_kapanis, usd_kapanis = kur_veri['Close']['GC=F'].dropna(), kur_veri['Close']['TRY=X'].dropna()
        guncel_ons, guncel_usd = float(ons_kapanis.iloc[-1]), float(usd_kapanis.iloc[-1])
        guncel_gr = (guncel_ons * guncel_usd) / 31.1034768
        onceki_ons = float(ons_kapanis.iloc[-2]) if len(ons_kapanis) > 1 else guncel_ons
        onceki_usd = float(usd_kapanis.iloc[-2]) if len(usd_kapanis) > 1 else guncel_usd
        onceki_gr = (onceki_ons * onceki_usd) / 31.1034768
        gunluk_yuzde = ((guncel_gr - onceki_gr) / onceki_gr) * 100 if onceki_gr > 0 else 0.0
        return guncel_gr, gunluk_yuzde
    except: return 0.0, 0.0

@st.cache_data(ttl=3600)
def kiyas_verilerini_getir(ekstra_hisseler=None):
    semboller = {
        "BİST100": "XU100.IS", 
        "BİST30": "XU030.IS", 
        "BİST50": "XU050.IS", 
        "BİST Tüm": "XUTUM.IS", 
        "Ons Altın": "GC=F"
    }
    
    if ekstra_hisseler:
        for h in ekstra_hisseler:
            if h:
                kod = h if h.endswith(".IS") else f"{h}.IS"
                semboller[h] = kod
                
    try:
        sembol_listesi = list(semboller.values())
        if len(sembol_listesi) > 1:
            toplu_veri = yf.download(sembol_listesi, period="5y", progress=False)
            if isinstance(toplu_veri.columns, pd.MultiIndex):
                if 'Close' in toplu_veri:
                    df_close = toplu_veri['Close'].copy()
                else:
                    return pd.DataFrame()
            else:
                if 'Close' in toplu_veri:
                    df_close = pd.DataFrame({sembol_listesi[0]: toplu_veri['Close']})
                else:
                    df_close = toplu_veri
        else:
            toplu_veri = yf.download(sembol_listesi[0], period="5y", progress=False)
            df_close = pd.DataFrame({sembol_listesi[0]: toplu_veri['Close']})

        df = df_close.reset_index()
        df = df.rename(columns={"index": "Tarih", "Date": "Tarih"})
        if "Tarih" in df.columns:
            df["Tarih"] = pd.to_datetime(df["Tarih"]).dt.date
            
        ters_semboller = {v: k for k, v in semboller.items()}
        df = df.rename(columns=ters_semboller)
        return df
    except Exception: 
        return pd.DataFrame()

PORTFOY_DOSYASI, GECMIS_DOSYASI, SABIT_VARLIK_DOSYASI = "portfoy.json", "portfoy_gecmis.json", "sabit_varliklar.json"

def portfoy_getir():
    veri = db_sync.load_data("portfoy", {"Ana Portföy": {}})
    if not veri: return {"Ana Portföy": {}}
    ilk_deger = list(veri.values())[0]
    if isinstance(ilk_deger, dict) and "maliyet" in ilk_deger:
        yeni_format = {"Ana Portföy": veri}; portfoy_kaydet(yeni_format); return yeni_format
    return veri

def portfoy_kaydet(veri):
    db_sync.save_data("portfoy", veri)

def gecmis_getir():
    return db_sync.load_data("portfoy_gecmis", {})

def gecmis_kaydet(veri):
    db_sync.save_data("portfoy_gecmis", veri)

def sabit_varlik_getir():
    return db_sync.load_data("sabit_varliklar", {"nakit": 0.0, "altin_gr": 0.0, "altin_maliyet": 0.0})

def sabit_varlik_kaydet(veri):
    db_sync.save_data("sabit_varliklar", veri)

portfoyler = portfoy_getir()
sabit_varliklar = sabit_varlik_getir()

# === BOZUK JSON ONARIM DÖNGÜSÜ ===
json_onari_yapildi = False
for cuzdan_adi, cuzdan_icerik in portfoyler.items():
    temiz_cuzdan = {}
    for varlik_kodu, detay in cuzdan_icerik.items():
        orijinal_kod = varlik_kodu
        
        # 1. URL Kalıntılarını Temizle
        if "fintables.com" in varlik_kodu:
            varlik_kodu = varlik_kodu.replace("https://fintables.com/sirketler/", "").replace("https://www.fintables.com/sirketler/", "").strip()
        if "tradingview.com" in varlik_kodu:
            varlik_kodu = varlik_kodu.split("BIST%3A")[-1].strip()
            
        # 2. Önceki Hatalı Kayıtlarda Düşen .IS Uzantısını Hisselere Geri Ekle
        if len(varlik_kodu) >= 4 and not varlik_kodu.endswith(".IS"):
            varlik_kodu += ".IS"
            
        # 3. Yanlışlıkla .IS Almış Fonları Kurtar (3 harf + .IS = 6 karakter)
        if varlik_kodu.endswith(".IS") and len(varlik_kodu) <= 6:
            varlik_kodu = varlik_kodu.replace(".IS", "")
            
        temiz_cuzdan[varlik_kodu] = detay
        if orijinal_kod != varlik_kodu:
            json_onari_yapildi = True
    portfoyler[cuzdan_adi] = temiz_cuzdan

if json_onari_yapildi: portfoy_kaydet(portfoyler)

ig_onari_yapildi = False
for cuzdan_adi, islemler in islem_gecmisi.items():
    for islem in islemler:
        v_adi = islem.get("Varlık", "")
        eski_v = v_adi
        if "fintables.com" in v_adi:
            v_adi = v_adi.replace("https://fintables.com/sirketler/", "").replace("https://www.fintables.com/sirketler/", "").strip()
        if "tradingview.com" in v_adi:
            v_adi = v_adi.split("BIST%3A")[-1].strip()
        if v_adi.endswith(".IS"):
            v_adi = v_adi.replace(".IS", "")
        if eski_v != v_adi:
            islem["Varlık"] = v_adi
            ig_onari_yapildi = True
if ig_onari_yapildi: islem_gecmisi_kaydet(islem_gecmisi)
# ==================================

# === OTOMATİK TAMAMLAMA İÇİN HİSSE LİSTESİ OLUŞTURMA ===
POPULER_BIST_HISSELERI = [
    "AKBNK", "AKSA", "AKSEN", "ALARK", "ALFAS", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", 
    "CANTE", "CCOLA", "CIMSA", "CWENE", "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO", "ENJSA", 
    "ENKAI", "EREGL", "EUPWR", "FROTO", "GARAN", "GESAN", "GUBRF", "GWIND", "HALKB", "HEKTS", 
    "ISCTR", "ISGYO", "ISMEN", "KCHOL", "KMPUR", "KONTR", "KORDS", "KOZAA", "KOZAL", "KRDMD", 
    "MGROS", "MIATK", "ODAS", "OTKAR", "OYAKC", "PETKM", "PGSUS", "QUAGR", "SAHOL", "SASA", 
    "SISE", "SKBNK", "SMRTG", "SOKM", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", 
    "TTKOM", "TTRAK", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE", "YKBNK", "YYLGD", "ZOREN",
    "KCAER", "YENIL", "KALES", "IZENR", "TATEN", "OFSYM", "ENSRI", "TRILC", "ALBRK"
]

tum_bilinen_hisseler = set(POPULER_BIST_HISSELERI)
for c_icerik in portfoyler.values():
    tum_bilinen_hisseler.update([k.replace('.IS', '') for k in c_icerik.keys() if k.endswith('.IS')])
TUM_HISSE_SECENEKLERI = sorted(list(tum_bilinen_hisseler))

def haric_cuzdanlari_getir():
    if os.path.exists("haric_cuzdanlar.json"):
        try:
            with open("haric_cuzdanlar.json", "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return []

def haric_cuzdanlari_kaydet(liste):
    with open("haric_cuzdanlar.json", "w", encoding="utf-8") as f: json.dump(liste, f)

haric_cuzdanlar = haric_cuzdanlari_getir()

with st.sidebar:
    st.markdown("### 🚫 Özetten Dışlananlar")
    haric_secim = st.multiselect("Ana sayfadan (Genel Toplam) gizlenecek cüzdanlar:", list(portfoyler.keys()), default=[c for c in haric_cuzdanlar if c in portfoyler])
    if set(haric_secim) != set(haric_cuzdanlar):
        haric_cuzdanlari_kaydet(haric_secim)
        st.rerun()
    st.markdown("---")
    st.markdown("### ⭐ Favori Hisseler")
    fav_veri_sidebar = favorileri_getir()
    if isinstance(fav_veri_sidebar, dict) and fav_veri_sidebar:
        for f_kod in fav_veri_sidebar.keys():
            if f_kod != "CACHE_DATE": st.markdown(f"- **{f_kod}**")
    elif isinstance(fav_veri_sidebar, list) and fav_veri_sidebar:
        for f_kod in fav_veri_sidebar:
            if f_kod != "CACHE_DATE": st.markdown(f"- **{f_kod}**")
    else: st.info("Favori hisseniz bulunmuyor.")
    st.markdown("---")

st.title("💼 Portföy ve Varlık Yönetimi")

SECENEK_OZET = "🌍 TÜM CÜZDANLAR (BÜYÜK RESİM)"
cuzdan_isimleri = [SECENEK_OZET] + list(portfoyler.keys())

c_cuzdan, c_hesapla, c_zirve, c_sinyal, c_kaydet, c_ekle, c_duzenle, c_sil = st.columns([1.8, 1.2, 0.9, 1.4, 1.0, 0.9, 0.9, 0.8])

with c_cuzdan: secili_cuzdan = st.selectbox("📂 Aktif Cüzdan Seçimi:", cuzdan_isimleri)

with c_hesapla:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Yeniden Hesapla", use_container_width=True): 
        canli_altin_getir.clear()
        bloomberg_fon_verilerini_cek.clear()
        st.session_state.sinyal_goster = False
        st.session_state.force_guncelleme = True 
        st.rerun()

with c_zirve:
    st.markdown("<div style='margin-top: 35px;'></div>", unsafe_allow_html=True)
    zirve_aktif = st.checkbox("🏔️ Zirve", key="zirve_hesap_kutusu", on_change=zirve_tetikle, help="Tarihi zirveleri (bölünme düzeltilmiş) hesaplar.")

with c_sinyal:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    
    taranabilir_hisseler = set()
    for c_icerik in portfoyler.values():
        taranabilir_hisseler.update([k for k in c_icerik.keys() if k.endswith('.IS')])
    
    menu_sinyal = st.popover("🎯 Sinyal Ayarları", use_container_width=True) if hasattr(st, "popover") else st.expander("🎯 Sinyal Ayarları")
    with menu_sinyal:
        if taranabilir_hisseler:
            st.markdown("### ⚙️ Analiz Ayarları")

            col_kriter1, col_kriter2 = st.columns(2)
            with col_kriter1:
                macd_istiyor_mu = st.checkbox("📈 MACD Onayı Zorunlu", value=st.session_state.get('p_macd', False))
                ema200_istiyor_mu = st.checkbox("📉 EMA200 Üzeri Zorunlu", value=st.session_state.get('p_ema', False))
                teknik_istiyor_mu = st.checkbox("🎯 Teknik Skorlama", value=st.session_state.get('p_tek', True))
            with col_kriter2:
                hacim_istiyor_mu = st.checkbox("📊 Hacim Onayı Zorunlu", value=st.session_state.get('p_hacim', False))
                ichimoku_istiyor_mu = st.checkbox("☁️ İçimoku Bulutu Zorunlu", value=st.session_state.get('p_ichi', False))
                nwe_istiyor_mu = st.checkbox("🌊 NWE (Nadaraya) Zorunlu", value=st.session_state.get('p_nwe', False))
            
            st.markdown("---")
            temel_istiyor_mu = st.checkbox("🏢 Temel Skor (Bilanço - Yavaş)", value=st.session_state.get('p_temel', False))
            
            st.markdown("---")
            if st.button("🚀 Seçili Ayarlarla Başlat", use_container_width=True, type="primary"):
                st.session_state['p_macd'] = macd_istiyor_mu
                st.session_state['p_ema'] = ema200_istiyor_mu
                st.session_state['p_hacim'] = hacim_istiyor_mu
                st.session_state['p_ichi'] = ichimoku_istiyor_mu
                st.session_state['p_nwe'] = nwe_istiyor_mu
                st.session_state['p_tek'] = teknik_istiyor_mu
                st.session_state['p_temel'] = temel_istiyor_mu
                st.session_state.force_guncelleme = True
                st.session_state.sinyal_goster = True
        else:
            st.info("Portföyde taranacak hisse bulunmuyor.")

with c_kaydet:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("💾 Günü Kaydet", use_container_width=True): 
        st.session_state.manuel_kayit_tetiklendi = True

if secili_cuzdan != SECENEK_OZET:
    with c_ekle:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        menu_ekle = st.popover("➕ Yeni", use_container_width=True) if hasattr(st, "popover") else st.expander("➕ Yeni")
        with menu_ekle:
            yeni_cuzdan_adi = st.text_input("Yeni Cüzdan Adı:", key="input_yeni_cuzdan")
            if st.button("Oluştur", use_container_width=True) and yeni_cuzdan_adi and yeni_cuzdan_adi not in portfoyler:
                portfoyler[yeni_cuzdan_adi] = {}; portfoy_kaydet(portfoyler); st.rerun()

    with c_duzenle:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        menu_duzenle = st.popover("✏️ İsim", use_container_width=True) if hasattr(st, "popover") else st.expander("✏️ İsim")
        with menu_duzenle:
            yeni_isim = st.text_input("Yeni Ad:", value=secili_cuzdan, key="input_ad_degistir")
            if st.button("Kaydet", use_container_width=True) and yeni_isim and yeni_isim != secili_cuzdan and yeni_isim not in portfoyler:
                portfoyler[yeni_isim] = portfoyler.pop(secili_cuzdan)
                if secili_cuzdan in cuzdan_bakiyeler: cuzdan_bakiyeler[yeni_isim] = cuzdan_bakiyeler.pop(secili_cuzdan)
                if secili_cuzdan in islem_gecmisi: islem_gecmisi[yeni_isim] = islem_gecmisi.pop(secili_cuzdan)
                portfoy_kaydet(portfoyler); bakiyeler_kaydet(cuzdan_bakiyeler); islem_gecmisi_kaydet(islem_gecmisi); st.rerun()

    with c_sil:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if len(portfoyler) > 1:
            menu_sil = st.popover("🗑️ Sil", use_container_width=True) if hasattr(st, "popover") else st.expander("🗑️ Sil")
            with menu_sil:
                st.error(f"**{secili_cuzdan}** kalıcı olarak silinecek. Emin misiniz?")
                if st.button("Evet, Sil", use_container_width=True, type="primary"):
                    del portfoyler[secili_cuzdan]
                    if secili_cuzdan in cuzdan_bakiyeler: del cuzdan_bakiyeler[secili_cuzdan]
                    if secili_cuzdan in islem_gecmisi: del islem_gecmisi[secili_cuzdan]
                    portfoy_kaydet(portfoyler); bakiyeler_kaydet(cuzdan_bakiyeler); islem_gecmisi_kaydet(islem_gecmisi); st.rerun()
        else: st.button("🗑️ Sil", disabled=True, use_container_width=True)

st.markdown("---")

tum_hisseler_set, tum_fonlar_set = set(), set()
taranacak_cuzdanlar = {}

if secili_cuzdan == SECENEK_OZET:
    for k, v in portfoyler.items():
        if k not in haric_cuzdanlar:
            taranacak_cuzdanlar[k] = v
else:
    taranacak_cuzdanlar = {secili_cuzdan: portfoyler[secili_cuzdan]}

for c_icerik in taranacak_cuzdanlar.values():
    tum_hisseler_set.update([k for k in c_icerik.keys() if k.endswith('.IS')])
    tum_fonlar_set.update([k for k in c_icerik.keys() if not k.endswith('.IS')])

taranacak_gecmis_cuzdanlar = {}
if secili_cuzdan == SECENEK_OZET:
    for k, v in islem_gecmisi.items():
        if k not in haric_cuzdanlar:
            taranacak_gecmis_cuzdanlar[k] = v
else:
    taranacak_gecmis_cuzdanlar = {secili_cuzdan: islem_gecmisi.get(secili_cuzdan, [])}

for g_cuzdan_adi, islem_listesi in taranacak_gecmis_cuzdanlar.items():
    for islem in islem_listesi:
        v_adi = islem.get("Varlık", "")
        if v_adi:
            if len(v_adi) <= 5 and v_adi.isalpha(): tum_hisseler_set.add(v_adi + ".IS")
            else: tum_fonlar_set.add(v_adi)

fiyatlar_hepsi = {}
if tum_hisseler_set or tum_fonlar_set:
    zorla_cek = st.session_state.pop("force_guncelleme", False) 
    sinyal_aktif = st.session_state.get("sinyal_goster", False)
    zirve_goster_aktif = st.session_state.get("zirve_hesap_kutusu", False)
    
    if zorla_cek or sinyal_aktif or zirve_goster_aktif:
        yukleme_metni = "🌐 Varlık verileri (Sinyal/Zirve) analiz ediliyor..." if (sinyal_aktif or zirve_goster_aktif) else "🔄 Tüm varlık verileri internetten zorla yenileniyor..."
        with st.spinner(yukleme_metni):
            fiyatlar_hepsi = varlik_fiyatlarini_getir(
                list(tum_hisseler_set), list(tum_fonlar_set), 
                sinyal_hesapla=sinyal_aktif,
                force_update=zorla_cek,
                macd_aktif=st.session_state.get("p_macd", False),
                ema200_aktif=st.session_state.get("p_ema", False),
                hacim_aktif=st.session_state.get("p_hacim", False),
                ichi_aktif=st.session_state.get("p_ichi", False),
                nwe_aktif=st.session_state.get("p_nwe", False),
                teknik_aktif=st.session_state.get("p_tek", True),
                temel_aktif=st.session_state.get("p_temel", False),
                zirve_hesapla=zirve_goster_aktif
            )
    else:
        fiyatlar_hepsi = varlik_fiyatlarini_getir(
            list(tum_hisseler_set), list(tum_fonlar_set), 
            sinyal_hesapla=False, force_update=False, zirve_hesapla=False
        )

canli_altin_fyt, canli_altin_yuzde = canli_altin_getir()

# ==========================================
# KAYIT MOTORU (GÜN SONU / MANUEL / HİSSE-FON AYRIMLI)
# ==========================================
simdi = datetime.now()
kapanis_saati = simdi.replace(hour=18, minute=20, second=0, microsecond=0)
bugun_str = simdi.strftime("%Y-%m-%d")
gecmis_verisi = gecmis_getir()

manuel_kayit_aktif = st.session_state.get("manuel_kayit_tetiklendi", False)
oto_kayit_aktif = (simdi.weekday() < 5) and (simdi >= kapanis_saati) and (bugun_str not in gecmis_verisi)

if manuel_kayit_aktif or oto_kayit_aktif:
    t_h_set, t_f_set = set(), set()
    for c_icerik in portfoyler.values():
        t_h_set.update([k for k in c_icerik.keys() if k.endswith('.IS')])
        t_f_set.update([k for k in c_icerik.keys() if not k.endswith('.IS')])
    
    t_fiyatlar = varlik_fiyatlarini_getir(list(t_h_set), list(t_f_set), sinyal_hesapla=False, force_update=False, zirve_hesapla=False)
    gunluk_kayit = {"GENEL_TOPLAM": {"yatirim": 0.0, "deger": 0.0, "hisse_yatirim": 0.0, "hisse_deger": 0.0, "fon_deger": 0.0, "altin_deger": 0.0, "takas_deger": 0.0, "nakit_deger": 0.0}}
    
    for c_adi, c_icerik in portfoyler.items():
        c_bakiye = cuzdan_bakiyeler.get(c_adi, {"nakit": 0.0, "takas": 0.0})
        c_nkt, c_tks = float(c_bakiye.get("nakit", 0.0)), float(c_bakiye.get("takas", 0.0))
        
        c_yat, c_deg, c_h_yat, c_h_deg = c_nkt + c_tks, c_nkt + c_tks, 0, 0
        for h, det in c_icerik.items():
            lot, mal = float(det["lot"]), float(det["maliyet"])
            fb = t_fiyatlar.get(h, {})
            fyt = fb.get("guncel", 0.0)
            if fyt <= 0: fyt = mal
            
            c_yat += lot * mal
            c_deg += lot * fyt
            
            if h.endswith('.IS'):
                c_h_yat += lot * mal
                c_h_deg += lot * fyt
                
        gunluk_kayit[c_adi] = {"yatirim": c_yat, "deger": c_deg, "hisse_yatirim": c_h_yat, "hisse_deger": c_h_deg, "fon_deger": (c_deg - c_h_deg - c_nkt - c_tks), "takas_deger": c_tks, "nakit_deger": c_nkt}
        
        if c_adi not in haric_cuzdanlar:
            gunluk_kayit["GENEL_TOPLAM"]["yatirim"] += c_yat
            gunluk_kayit["GENEL_TOPLAM"]["deger"] += c_deg
            gunluk_kayit["GENEL_TOPLAM"]["hisse_yatirim"] += c_h_yat
            gunluk_kayit["GENEL_TOPLAM"]["hisse_deger"] += c_h_deg
            gunluk_kayit["GENEL_TOPLAM"]["fon_deger"] += (c_deg - c_h_deg - c_nkt - c_tks)
            gunluk_kayit["GENEL_TOPLAM"]["takas_deger"] += c_tks
            gunluk_kayit["GENEL_TOPLAM"]["nakit_deger"] += c_nkt
    
    s_nakit = float(sabit_varliklar.get("nakit", 0.0))
    s_altin_gr = float(sabit_varliklar.get("altin_gr", 0.0))
    s_altin_mal = float(sabit_varliklar.get("altin_maliyet", 0.0))
    a_fyt = canli_altin_fyt if canli_altin_fyt > 0 else s_altin_mal
    s_altin_yatirim = s_altin_gr * s_altin_mal; s_altin_deger = s_altin_gr * a_fyt
    
    gunluk_kayit["GENEL_TOPLAM"]["yatirim"] += (s_nakit + s_altin_yatirim)
    gunluk_kayit["GENEL_TOPLAM"]["deger"] += (s_nakit + s_altin_deger)
    gunluk_kayit["GENEL_TOPLAM"]["altin_deger"] = s_altin_deger
    gunluk_kayit["GENEL_TOPLAM"]["nakit_deger"] += s_nakit
    
    if bugun_str not in gecmis_verisi: gecmis_verisi[bugun_str] = gunluk_kayit
    else:
        for k, v in gunluk_kayit.items():
            if k not in gecmis_verisi[bugun_str]: gecmis_verisi[bugun_str][k] = {}
            gecmis_verisi[bugun_str][k]["yatirim"] = v["yatirim"]
            gecmis_verisi[bugun_str][k]["deger"] = v["deger"]
            gecmis_verisi[bugun_str][k]["hisse_yatirim"] = v.get("hisse_yatirim", 0)
            gecmis_verisi[bugun_str][k]["hisse_deger"] = v.get("hisse_deger", 0)
            gecmis_verisi[bugun_str][k]["fon_deger"] = v.get("fon_deger", 0)
            gecmis_verisi[bugun_str][k]["altin_deger"] = v.get("altin_deger", 0)
            gecmis_verisi[bugun_str][k]["takas_deger"] = v.get("takas_deger", 0)
            gecmis_verisi[bugun_str][k]["nakit_deger"] = v.get("nakit_deger", 0)
            
    gecmis_kaydet(gecmis_verisi)
    if manuel_kayit_aktif:
        st.session_state.manuel_kayit_tetiklendi = False
        st.toast("✅ Günün portföy durumu başarıyla kaydedildi/güncellendi!", icon="✅")

# ==========================================
# 🌍 MOD 1: TÜM CÜZDANLAR ÖZETİ
# ==========================================
if secili_cuzdan == SECENEK_OZET:
    st.subheader("🌍 Tüm Varlıkların Genel Özeti")
    
    hatali_varliklar_genel = set()
    cuzdan_ozetleri = {}
    birlesik_veriler = {}
    toplam_yatirim_genel, toplam_deger_genel = 0, 0
    toplam_nakit_genel, toplam_takas_genel = 0, 0
    cuzdan_agirliklari = {k: 0 for k in portfoyler.keys()}

    for c_adi, c_icerik in portfoyler.items():
        if c_adi in haric_cuzdanlar: continue
        
        c_bakiye = cuzdan_bakiyeler.get(c_adi, {"nakit": 0.0, "takas": 0.0})
        c_nkt, c_tks = float(c_bakiye.get("nakit", 0.0)), float(c_bakiye.get("takas", 0.0))
        
        toplam_nakit_genel += c_nkt
        toplam_takas_genel += c_tks
        
        toplam_yatirim_genel += (c_nkt + c_tks)
        toplam_deger_genel += (c_nkt + c_tks)
        cuzdan_agirliklari[c_adi] += (c_nkt + c_tks)
        
        c_yat_toplam, c_deg_toplam = c_nkt + c_tks, c_nkt + c_tks
        for hisse, detay in c_icerik.items():
            lot, maliyet = float(detay["lot"]), float(detay["maliyet"])
            
            alim_str = detay.get("alim_tarihi", datetime.today().strftime("%Y-%m-%d"))
            try: alim_tarihi_obj = datetime.strptime(alim_str, "%Y-%m-%d").date()
            except: alim_tarihi_obj = datetime.today().date()
            
            fiyat_bilgisi = fiyatlar_hepsi.get(hisse, {"guncel": 0.0, "onceki": maliyet, "destek":0, "direnc":0, "hedef_pot":0, "stop_marji":0, "sinyal": "➖", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": 0.0, "zirve_gun": 0})
            
            guncel_fiyat = fiyat_bilgisi["guncel"]
            if guncel_fiyat <= 0: hatali_varliklar_genel.add(hisse.replace('.IS', ''))
                
            onceki_fiyat = fiyat_bilgisi.get("onceki", maliyet)
            gunluk_degisim = ((guncel_fiyat - onceki_fiyat) / onceki_fiyat * 100) if onceki_fiyat > 0 else 0
            
            t_maliyet, g_deger = lot * maliyet, lot * guncel_fiyat
            c_yat_toplam += t_maliyet; c_deg_toplam += g_deger
            
            toplam_yatirim_genel += t_maliyet; toplam_deger_genel += g_deger
            cuzdan_agirliklari[c_adi] += g_deger
            
            if hisse not in birlesik_veriler:
                birlesik_veriler[hisse] = {
                    "Lot": 0, "toplam_maliyet": 0, "cuzdanlar": [], "guncel_fiyat": guncel_fiyat, "gunluk_degisim": gunluk_degisim, 
                    "tip": "Hisse Senedi" if hisse.endswith(".IS") else "Yatırım Fonu",
                    "baz_alim_tarihi": alim_tarihi_obj,
                    "max_lot": lot,
                    "destek": fiyat_bilgisi.get("destek", 0), "direnc": fiyat_bilgisi.get("direnc", 0),
                    "hedef_pot": fiyat_bilgisi.get("hedef_pot", 0), "stop_marji": fiyat_bilgisi.get("stop_marji", 0),
                    "sinyal": fiyat_bilgisi.get("sinyal", "➖"),
                    "teknik_skor": fiyat_bilgisi.get("teknik_skor", 0), "temel_skor": fiyat_bilgisi.get("temel_skor", 0),
                    "zirve_uzaklik_yuzde": fiyat_bilgisi.get("zirve_uzaklik_yuzde", 0.0),
                    "zirve_gun": fiyat_bilgisi.get("zirve_gun", 0)
                }
            else:
                if lot > birlesik_veriler[hisse]["max_lot"]:
                    birlesik_veriler[hisse]["max_lot"] = lot
                    birlesik_veriler[hisse]["baz_alim_tarihi"] = alim_tarihi_obj
                    
            birlesik_veriler[hisse]["Lot"] += lot; birlesik_veriler[hisse]["toplam_maliyet"] += t_maliyet
            if c_adi not in birlesik_veriler[hisse]["cuzdanlar"]: birlesik_veriler[hisse]["cuzdanlar"].append(c_adi)
            
        cuzdan_ozetleri[c_adi] = {"yatirim": c_yat_toplam, "deger": c_deg_toplam}

    n_tl = float(sabit_varliklar.get("nakit", 0.0))
    a_gr = float(sabit_varliklar.get("altin_gr", 0.0))
    a_mal = float(sabit_varliklar.get("altin_maliyet", 0.0))
    a_guncel_fyt = canli_altin_fyt if canli_altin_fyt > 0 else a_mal
    a_yatirim, a_deger = a_gr * a_mal, a_gr * a_guncel_fyt
    
    toplam_nakit_genel += n_tl
    toplam_yatirim_genel += (n_tl + a_yatirim)
    toplam_deger_genel += (n_tl + a_deger)
    
    if (n_tl + a_yatirim) > 0 or (n_tl + a_deger) > 0:
        cuzdan_ozetleri["Sabit Varlıklar (Nakit & Altın)"] = {"yatirim": n_tl + a_yatirim, "deger": n_tl + a_deger}
        
    genel_kz_tl = toplam_deger_genel - toplam_yatirim_genel
    genel_kz_yuzde = ((toplam_deger_genel - toplam_yatirim_genel) / toplam_yatirim_genel * 100) if toplam_yatirim_genel > 0 else 0

    if hatali_varliklar_genel:
        st.error(f"⚠️ **DİKKAT:** Aşağıdaki varlıkların fiyatı bağlantı sorunu nedeniyle çekilemedi (0 TL olarak görünüyor): **{', '.join(list(hatali_varliklar_genel))}**. Lütfen yukarıdaki '🔄 Yeniden Hesapla' butonuna basarak tekrar deneyin.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 TOPLAM YATIRIM", f"{tr_format(toplam_yatirim_genel)} ₺")
    m2.metric("📈 GÜNCEL PORTFÖY", f"{tr_format(toplam_deger_genel)} ₺")
    m3.metric("💸 KÂR/ZARAR (TL)", f"{tr_format(genel_kz_tl)} ₺", delta_color="normal" if genel_kz_tl >= 0 else "inverse")
    yuzde_str = f"% {tr_format(genel_kz_yuzde)}"
    m4.metric("📊 KÂR/ZARAR (%)", yuzde_str, delta=yuzde_str if genel_kz_yuzde >= 0 else yuzde_str, delta_color="normal" if genel_kz_yuzde >= 0 else "inverse")
    
    st.markdown("<br>", unsafe_allow_html=True)
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("💵 TOPLAM NAKİT", f"{tr_format(toplam_nakit_genel)} ₺")
    n2.metric("⏳ TOPLAM TAKAS", f"{tr_format(toplam_takas_genel)} ₺")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📊 Cüzdan Performans Özeti")
    
    co_liste = []
    for c_ad, c_ver in cuzdan_ozetleri.items():
        cyat = c_ver["yatirim"]; cdeg = c_ver["deger"]; ckz = cdeg - cyat
        ckz_y = (ckz / cyat * 100) if cyat > 0 else 0
        durum = "🟢" if ckz > 0 else ("🔴" if ckz < 0 else "⚪")
        co_liste.append({
            "Durum": durum, "Cüzdan Adı": c_ad, "Toplam Yatırım": cyat, 
            "Güncel Değer": cdeg, "K/Z (TL)": ckz, "K/Z (%)": ckz_y
        })
        
    if co_liste:
        st.dataframe(
            pd.DataFrame(co_liste),
            column_config={
                "Toplam Yatırım": st.column_config.NumberColumn("Toplam Yatırım", format="%,.2f ₺"),
                "Güncel Değer": st.column_config.NumberColumn("Güncel Değer", format="%,.2f ₺"),
                "K/Z (TL)": st.column_config.NumberColumn("K/Z (TL)", format="%,.2f ₺"),
                "K/Z (%)": st.column_config.NumberColumn("K/Z (%)", format="%% %,.2f")
            },
            use_container_width=True, hide_index=True
        )

    st.markdown("---")
    with st.expander("💵 Sabit Varlıklar (Nakit & Altın) Düzenle", expanded=False):
        c_n, c_agr, c_amal, c_btn = st.columns([1.5, 1.5, 1.5, 1.5])
        with c_n: yeni_nakit = st.number_input("Nakit Varlık (TL):", value=float(sabit_varliklar.get("nakit", 0.0)), step=1000.0, format="%.2f")
        with c_agr: yeni_altin_gr = st.number_input("Gram Altın (Adet):", value=float(sabit_varliklar.get("altin_gr", 0.0)), step=1.0, format="%.2f")
        with c_amal: yeni_altin_mal = st.number_input("Altın Maliyeti (TL/Gr):", value=float(sabit_varliklar.get("altin_maliyet", 0.0)), step=100.0, format="%.2f")
        with c_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Kaydet ve Güncelle", type="primary", use_container_width=True):
                sabit_varliklar["nakit"] = yeni_nakit; sabit_varliklar["altin_gr"] = yeni_altin_gr; sabit_varliklar["altin_maliyet"] = yeni_altin_mal
                sabit_varlik_kaydet(sabit_varliklar); st.rerun()

    tablo_ozet = []
    
    for c_adi, b_detay in cuzdan_bakiyeler.items():
        if c_adi in haric_cuzdanlar: continue
        
        b_nkt, b_tks = float(b_detay.get("nakit", 0.0)), float(b_detay.get("takas", 0.0))
        if b_nkt > 0:
            tablo_ozet.append({
                "Seç": False, "Durum": "⚪", "Tip": "Nakit", "Varlık": f"Nakit ({c_adi})", "Sinyal": "➖ Nakit", "Günlük (%)": 0.0,
                "Alım Tarihi": None, "Gün": 0,
                "Lot": b_nkt, "Maliyet": 1.0, "Güncel Fiyat": 1.0, "Destek": 0.0, "Direnç": 0.0, "Hedef (%)": 0.0, "Stop (%)": 0.0,
                "Toplam Yatırım": b_nkt, "Güncel Değer": b_nkt, "K/Z (TL)": 0.0, "K/Z (%)": 0.0, 
                "Ort. Getiri (%)": 0.0, "Zirveye Uzaklık (%)": 0.0, "Zirve (Gün)": 0,
                "Bulunduğu Cüzdanlar": c_adi,
                "Teknik Skor": 0, "Temel Skor": 0
            })
        if b_tks > 0:
            tablo_ozet.append({
                "Seç": False, "Durum": "⚪", "Tip": "Nakit", "Varlık": f"Takas ({c_adi})", "Sinyal": "➖ Takas", "Günlük (%)": 0.0,
                "Alım Tarihi": None, "Gün": 0,
                "Lot": b_tks, "Maliyet": 1.0, "Güncel Fiyat": 1.0, "Destek": 0.0, "Direnç": 0.0, "Hedef (%)": 0.0, "Stop (%)": 0.0,
                "Toplam Yatırım": b_tks, "Güncel Değer": b_tks, "K/Z (TL)": 0.0, "K/Z (%)": 0.0, 
                "Ort. Getiri (%)": 0.0, "Zirveye Uzaklık (%)": 0.0, "Zirve (Gün)": 0,
                "Bulunduğu Cüzdanlar": c_adi,
                "Teknik Skor": 0, "Temel Skor": 0
            })
    
    if n_tl > 0:
        tablo_ozet.append({
            "Seç": False, "Durum": "⚪", "Tip": "Nakit", "Varlık": "Nakit TL", "Sinyal": "➖ Nakit", "Günlük (%)": 0.0,
            "Alım Tarihi": None, "Gün": 0,
            "Lot": n_tl, "Maliyet": 1.0, "Güncel Fiyat": 1.0, "Destek": 0.0, "Direnç": 0.0, "Hedef (%)": 0.0, "Stop (%)": 0.0,
            "Toplam Yatırım": n_tl, "Güncel Değer": n_tl, "K/Z (TL)": 0.0, "K/Z (%)": 0.0, 
            "Ort. Getiri (%)": 0.0, "Zirveye Uzaklık (%)": 0.0, "Zirve (Gün)": 0,
            "Bulunduğu Cüzdanlar": "Sabit Varlıklar",
            "Teknik Skor": 0, "Temel Skor": 0
        }); cuzdan_agirliklari["Sabit Varlıklar"] = cuzdan_agirliklari.get("Sabit Varlıklar", 0) + n_tl
        
    if a_gr > 0:
        a_kz_tl = a_deger - a_yatirim
        a_kz_yuzde = ((a_guncel_fyt - a_mal) / a_mal * 100) if a_mal > 0 else 0
        tablo_ozet.append({
            "Seç": False, "Durum": "🟢" if a_kz_tl > 0 else ("🔴" if a_kz_tl < 0 else "⚪"), "Tip": "Emtia (Altın)", "Varlık": "Gram Altın", "Sinyal": "➖ Emtia", "Günlük (%)": canli_altin_yuzde,
            "Alım Tarihi": None, "Gün": 0,
            "Lot": a_gr, "Maliyet": round(a_mal, 2), "Güncel Fiyat": round(a_guncel_fyt, 2), "Destek": 0.0, "Direnç": 0.0, "Hedef (%)": 0.0, "Stop (%)": 0.0,
            "Toplam Yatırım": a_yatirim, "Güncel Değer": a_deger, "K/Z (TL)": a_kz_tl, "K/Z (%)": a_kz_yuzde, 
            "Ort. Getiri (%)": 0.0, "Zirveye Uzaklık (%)": 0.0, "Zirve (Gün)": 0,
            "Bulunduğu Cüzdanlar": "Sabit Varlıklar",
            "Teknik Skor": 0, "Temel Skor": 0
        }); cuzdan_agirliklari["Sabit Varlıklar"] = cuzdan_agirliklari.get("Sabit Varlıklar", 0) + a_deger

    for hisse, veri in birlesik_veriler.items():
        toplam_lot = veri["Lot"]
        agirlikli_maliyet = veri["toplam_maliyet"] / toplam_lot if toplam_lot > 0 else 0
        g_fiyat = veri["guncel_fiyat"]
        guncel_deger = toplam_lot * g_fiyat
        kz_tl = guncel_deger - veri["toplam_maliyet"]
        kz_yuzde = ((g_fiyat - agirlikli_maliyet) / agirlikli_maliyet * 100) if agirlikli_maliyet > 0 else 0
        
        baz_alim = veri["baz_alim_tarihi"]
        try: elde_tutma = len(pd.bdate_range(start=baz_alim, end=datetime.today().date()))
        except: elde_tutma = 0
            
        tablo_ozet.append({
            "Seç": False, "Durum": "🟢" if kz_tl > 0 else ("🔴" if kz_tl < 0 else "⚪"), "Tip": veri["tip"], "Varlık": hisse.replace(".IS", ""), "Sinyal": veri["sinyal"], "Günlük (%)": veri["gunluk_degisim"],
            "Alım Tarihi": baz_alim, "Gün": elde_tutma,
            "Lot": toplam_lot, "Maliyet": round(agirlikli_maliyet, 2) if veri["tip"] == "Hisse Senedi" else round(agirlikli_maliyet, 6), 
            "Güncel Fiyat": round(g_fiyat, 2) if veri["tip"] == "Hisse Senedi" else round(g_fiyat, 6), 
            "Destek": round(veri["destek"], 2) if veri["tip"] == "Hisse Senedi" else 0.0, 
            "Direnç": round(veri["direnc"], 2) if veri["tip"] == "Hisse Senedi" else 0.0, 
            "Hedef (%)": veri["hedef_pot"], "Stop (%)": veri["stop_marji"],
            "Toplam Yatırım": veri["toplam_maliyet"], "Güncel Değer": guncel_deger, "K/Z (TL)": kz_tl, 
            "K/Z (%)": kz_yuzde, 
            "Ort. Getiri (%)": (kz_yuzde / elde_tutma) if elde_tutma > 0 else kz_yuzde,
            "Zirveye Uzaklık (%)": veri.get("zirve_uzaklik_yuzde", 0.0),
            "Zirve (Gün)": veri.get("zirve_gun", 0),
            "Bulunduğu Cüzdanlar": ", ".join(veri["cuzdanlar"]),
            "Teknik Skor": veri["teknik_skor"], "Temel Skor": veri["temel_skor"]
        })

    if tablo_ozet:
        df_ozet = pd.DataFrame(tablo_ozet)
        st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
        
        c_baslik, c_ara, c_sira, c_tog = st.columns([2.5, 1.5, 2, 1.2])
        with c_baslik:
            st.markdown("<p style='font-size: 17px; font-weight: bold; margin-top: 8px;'>BİRLEŞTİRİLMİŞ VARLIK DAĞILIMI (Ağırlıklı Maliyete Göre)</p>", unsafe_allow_html=True)
        with c_ara:
            ara_mod1 = st.text_input("Ara", key="ara_mod1", label_visibility="collapsed", placeholder="🔍 Varlık Ara...").upper()
        with c_sira:
            siralama_secimi_genel = st.selectbox(
                "Sırala",
                ["💰 Güncel Değer (Yüksekten Düşüğe)", "🔤 A'dan Z'ye (Varlık Adı)", "🎯 Teknik Puana Göre", "🚦 Sinyale Göre", "📈 En Çok Kâr Edenler (%)", "📉 En Çok Zarar Edenler (%)", "🔥 Günlük Kazandıranlar (%)"],
                index=0, key="sira_genel", label_visibility="collapsed"
            )
        with c_tog:
            st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
            tumunu_goster_m1 = st.toggle("Tüm Varlıkları", value=False)
            
        df_f = df_ozet.copy()
        if not tumunu_goster_m1: df_f = df_f[df_f["Tip"] == "Hisse Senedi"]
        if ara_mod1: df_f = df_f[df_f["Varlık"].str.contains(ara_mod1)]
            
        if "A'dan Z'ye" in siralama_secimi_genel: df_f = df_f.sort_values(by="Varlık", ascending=True)
        elif "Güncel Değer" in siralama_secimi_genel: df_f = df_f.sort_values(by="Güncel Değer", ascending=False)
        elif "Teknik Puan" in siralama_secimi_genel: df_f = df_f.sort_values(by="Teknik Skor", ascending=False)
        elif "Sinyale Göre" in siralama_secimi_genel:
            sinyal_sira = {"⚡ GÜÇLÜ AL (KV)": 1, "🛡️ GÜÇLÜ AL (OV)": 2, "🚀 GÜÇLÜ AL": 3, "🌱 KADEMELİ": 4, "⏳ BEKLE": 5, "⚠️ KÂR AL": 6, "⛔ SAT": 7}
            df_f['Sinyal_Sira'] = df_f['Sinyal'].map(lambda x: sinyal_sira.get(x, 99))
            df_f = df_f.sort_values(by=["Sinyal_Sira", "Güncel Değer"], ascending=[True, False]).drop(columns=['Sinyal_Sira'])
        elif "En Çok Kâr" in siralama_secimi_genel: df_f = df_f.sort_values(by="K/Z (%)", ascending=False)
        elif "En Çok Zarar" in siralama_secimi_genel: df_f = df_f.sort_values(by="K/Z (%)", ascending=True)
        elif "Günlük Kazandıranlar" in siralama_secimi_genel: df_f = df_f.sort_values(by="Günlük (%)", ascending=False)

        df_f = df_f.reset_index(drop=True)
        df_f.insert(0, "#", range(1, len(df_f) + 1))
        
        if not df_f.empty:
            sinyal_sutunu_aktif = st.session_state.get("sinyal_goster", False)
            tablo_yuksekligi = max(750, int((len(df_f) + 1) * 36 + 40))
            
            if "master_sec_ozet" not in st.session_state: st.session_state["master_sec_ozet"] = False
            
            c_sec1, c_sec2, _ = st.columns([1.5, 1.5, 7])
            with c_sec1:
                if st.button("☑️ Tümünü Seç", key="btn_sec_tum_ozet"):
                    st.session_state["master_sec_ozet"] = True
                    if "editor_ozet_tablosu" in st.session_state: del st.session_state["editor_ozet_tablosu"]
                    st.rerun()
            with c_sec2:
                if st.button("🔲 Seçimi Kaldır", key="btn_kaldir_ozet"):
                    st.session_state["master_sec_ozet"] = False
                    if "editor_ozet_tablosu" in st.session_state: del st.session_state["editor_ozet_tablosu"]
                    st.rerun()
            
            df_f["Seç"] = st.session_state["master_sec_ozet"]
            
            tum_olasi_sutunlar = [c for c in df_f.columns if c not in ["Seç", "🗑️ Sil", "#"]]
            if not sinyal_sutunu_aktif:
                sinyal_kolonlari = ["Sinyal", "Destek", "Direnç", "Hedef (%)", "Stop (%)", "Teknik Skor", "Temel Skor"]
                tum_olasi_sutunlar = [c for c in tum_olasi_sutunlar if c not in sinyal_kolonlari]

            if not st.session_state.get("zirve_hesap_kutusu", False):
                if "Zirveye Uzaklık (%)" in tum_olasi_sutunlar: tum_olasi_sutunlar.remove("Zirveye Uzaklık (%)")
                if "Zirve (Gün)" in tum_olasi_sutunlar: tum_olasi_sutunlar.remove("Zirve (Gün)")

            if not st.session_state.get("p_temel", False) and "Temel Skor" in tum_olasi_sutunlar:
                tum_olasi_sutunlar.remove("Temel Skor")
            if not st.session_state.get("p_tek", True) and "Teknik Skor" in tum_olasi_sutunlar:
                tum_olasi_sutunlar.remove("Teknik Skor")

            kayitli_sutun_ayarlari = portfoy_sutun_ayarlari_getir()
            for s in tum_olasi_sutunlar:
                chk_key = f"pchk_{s}"
                if chk_key not in st.session_state:
                    varsayilan_gizli = ["Destek", "Direnç", "Hedef (%)", "Stop (%)"]
                    st.session_state[chk_key] = kayitli_sutun_ayarlari.get(chk_key, s not in varsayilan_gizli)

            with st.expander("👁️ Sütunları Gizle / Göster Paneli", expanded=False):
                st.markdown("Tabloda görmek istediğiniz sütunları seçin:")
                cb_s1, cb_s2 = st.columns(2)
                if cb_s1.button("✅ Tümünü Göster", key="show_all_cols_mod1"):
                    for s in tum_olasi_sutunlar: st.session_state[f"pchk_{s}"] = True
                    portfoy_sutun_degisti(); st.rerun()
                if cb_s2.button("❌ Tümünü Gizle", key="hide_all_cols_mod1"):
                    for s in tum_olasi_sutunlar: 
                        if s not in ["Varlık", "Durum", "Tip"]: st.session_state[f"pchk_{s}"] = False
                    portfoy_sutun_degisti(); st.rerun()
                
                st.markdown("---")
                grid = st.columns(6)
                for i, s in enumerate(tum_olasi_sutunlar):
                    grid[i % 6].checkbox(s, key=f"pchk_{s}", on_change=portfoy_sutun_degisti)

            sec_cols = [s for s in tum_olasi_sutunlar if st.session_state.get(f"pchk_{s}", True)]
            
            saga_alinacaklar = ["Teknik Skor", "Temel Skor", "Sinyal", "Bulunduğu Cüzdanlar"]
            for col in saga_alinacaklar:
                if col in sec_cols:
                    sec_cols.remove(col)
                    sec_cols.append(col)
                
            gosterilecek_sutunlar = [c for c in ["Seç", "🗑️ Sil", "#"] if c in df_f.columns] + sec_cols
            df_gosterim = df_f[gosterilecek_sutunlar].copy()

            if "Teknik Skor" in df_gosterim.columns: df_gosterim["Teknik Skor"] = pd.to_numeric(df_gosterim["Teknik Skor"], errors='coerce').fillna(0).astype(int)
            if "Temel Skor" in df_gosterim.columns: df_gosterim["Temel Skor"] = pd.to_numeric(df_gosterim["Temel Skor"], errors='coerce').fillna(0).astype(int)

            col_conf = {
                "Seç": st.column_config.CheckboxColumn("Seç", default=False, width=40),
                "#": st.column_config.NumberColumn("#", format="%d", disabled=True, width=30),
                "Durum": st.column_config.TextColumn("Durum", disabled=True, width=50),
                "Tip": st.column_config.TextColumn("Tip", disabled=True, width=80),
                "Varlık": st.column_config.TextColumn("Varlık", disabled=True, width=70),
                "Alım Tarihi": st.column_config.DateColumn("Alım", format="DD.MM.YYYY", disabled=True, width=80),
                "Gün": st.column_config.NumberColumn("Gün", disabled=True, width=45),
                "Günlük (%)": st.column_config.NumberColumn("Günlük (%)", format="%% %,.2f", width="small", disabled=True),
                "Lot": st.column_config.NumberColumn("Lot", format=None, width=40, disabled=True),
                "Maliyet": st.column_config.NumberColumn("Maliyet", format=None, width=58, disabled=True),
                "Güncel Fiyat": st.column_config.NumberColumn("Fiyat", format=None, width=58, disabled=True),
                "Toplam Yatırım": st.column_config.NumberColumn("Toplam Yatırım", format="%,.2f ₺", disabled=True, width=100),
                "Güncel Değer": st.column_config.NumberColumn("Güncel Değer", format="%,.2f ₺", disabled=True, width=100),
                "K/Z (TL)": st.column_config.NumberColumn("K/Z (TL)", format="%,.2f ₺", disabled=True, width=100),
                "K/Z (%)": st.column_config.NumberColumn("K/Z (%)", format="%% %,.2f", disabled=True, width=85),
                "Ort. Getiri (%)": st.column_config.NumberColumn("Ort. Getiri (%)", format="%% %,.2f", disabled=True, width=80),
                "Zirveye Uzaklık (%)": st.column_config.NumberColumn("Zirveye Uzaklık (%)", format="%% %,.2f", disabled=True, width=90),
                "Zirve (Gün)": st.column_config.NumberColumn("Zirve (Gün)", format="%d", disabled=True, width=70),
                "Bulunduğu Cüzdanlar": st.column_config.TextColumn("Cüzdanlar", disabled=True),
                "Sinyal": st.column_config.TextColumn("Sinyal", disabled=True, width=90),
                "Destek": st.column_config.NumberColumn("Destek", format=None, disabled=True, width=65),
                "Direnç": st.column_config.NumberColumn("Direnç", format=None, disabled=True, width=65),
                "Hedef (%)": st.column_config.NumberColumn("Hedef (%)", format="%% %,.2f", disabled=True, width=70),
                "Stop (%)": st.column_config.NumberColumn("Stop (%)", format="%% %,.2f", disabled=True, width=70)
            }
            if "Teknik Skor" in sec_cols: col_conf["Teknik Skor"] = st.column_config.ProgressColumn("Teknik Puan", format="%d", min_value=0, max_value=100, width=117)
            if "Temel Skor" in sec_cols: col_conf["Temel Skor"] = st.column_config.ProgressColumn("Temel Kalite", format="%d", min_value=0, max_value=100, width=90)

            edited_df_ozet = st.data_editor(
                df_gosterim,
                column_config=col_conf,
                use_container_width=True, hide_index=True, height=tablo_yuksekligi,
                key="editor_ozet_tablosu"
            )
            
            secilen_ozet = edited_df_ozet[edited_df_ozet["Seç"] == True]
            if not secilen_ozet.empty:
                s_yat_ozet = secilen_ozet["Toplam Yatırım"].sum()
                s_deg_ozet = secilen_ozet["Güncel Değer"].sum()
                s_kz_ozet = s_deg_ozet - s_yat_ozet
                s_kzy_ozet = (s_kz_ozet / s_yat_ozet * 100) if s_yat_ozet > 0 else 0
                st.success(f"🎯 **SEÇİLİ VARLIKLAR TOPLAMI:** Toplam Yatırım: **{tr_format(s_yat_ozet)} ₺** | Güncel Değer: **{tr_format(s_deg_ozet)} ₺** | K/Z: **{tr_format(s_kz_ozet)} ₺** (% {tr_format(s_kzy_ozet)})")

            st.markdown("---")
            c_pasta1, c_pasta2 = st.columns(2)
            renk_ayari = {"Hisse Senedi": "#2E86C1", "Yatırım Fonu": "#8E44AD", "Emtia (Altın)": "#F1C40F", "Nakit": "#27AE60"}
            
            with c_pasta1:
                st.subheader("🥧 Varlık Sınıfı Dağılımı")
                df_sinif = df_f.groupby('Tip')['Güncel Değer'].sum().reset_index()
                fig1 = px.pie(df_sinif, values='Güncel Değer', names='Tip', hole=0.4, color_discrete_map=renk_ayari)
                fig1.update_traces(textposition='inside', textinfo='percent+label')
                fig1.update_layout(margin=dict(t=20, b=0, l=0, r=0), height=350)
                st.plotly_chart(fig1, use_container_width=True)
                    
            with c_pasta2:
                st.subheader("🥧 Genel Varlık Ağırlıkları (Tekil)")
                fig2 = px.pie(df_f, values='Güncel Değer', names='Varlık', hole=0.4, color_discrete_sequence=px.colors.sequential.Plasma)
                fig2.update_traces(textposition='inside', textinfo='percent+label')
                fig2.update_layout(margin=dict(t=20, b=0, l=0, r=0), height=350)
                st.plotly_chart(fig2, use_container_width=True)
        else: st.warning("Seçilen filtreye uygun varlık bulunamadı.")
            
        # ========================================================
        if gecmis_verisi:
            st.markdown("---")
            col_g1, col_g2, col_g3 = st.columns(3)
            with col_g1:
                st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>Grafik Eğrisi:</p>", unsafe_allow_html=True)
                grafik_turu1 = st.radio("Grafik Eğrisi:", ["Güncel Değer (TL)", "Kâr/Zarar (%)"], horizontal=True, key="gr_tur1", label_visibility="collapsed")
            with col_g2:
                st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>📊 Endeks Kıyasla:</p>", unsafe_allow_html=True)
                kiyaslamalar1 = st.multiselect("Endeks Kıyasla", ["BİST100", "BİST30", "BİST50", "BİST Tüm", "Ons Altın"], key="kiyas_mod1", label_visibility="collapsed")
            with col_g3:
                st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>➕ Hisse Kıyasla (Arama):</p>", unsafe_allow_html=True)
                ozel_kiyas_hisse1 = st.multiselect("Hisse Kıyasla", TUM_HISSE_SECENEKLERI, key="ozel_kiyas_mod1", placeholder="Hisse ara (Örn: THYAO)", label_visibility="collapsed")
            
            hedef_anahtar = "GENEL_TOPLAM"
            grafik_verisi = [{
                "Tarih": t, 
                "Kâr/Zarar (%)": round(((d[hedef_anahtar]["deger"] - d[hedef_anahtar]["yatirim"]) / d[hedef_anahtar]["yatirim"] * 100), 2) if d[hedef_anahtar].get("yatirim", 0) > 0 else 0.0, 
                "Güncel Değer (TL)": d[hedef_anahtar].get("deger", 0.0),
                "Yatırım Tutarı": f"{d[hedef_anahtar].get('yatirim', 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"
            } for t, d in gecmis_verisi.items() if hedef_anahtar in d]
                    
            if grafik_verisi:
                df_gecmis = pd.DataFrame(grafik_verisi); df_gecmis["Tarih"] = pd.to_datetime(df_gecmis["Tarih"]); df_gecmis = df_gecmis.sort_values(by="Tarih")
                zaman_filtresi = st.selectbox("⏳ Görüntülenecek Periyot:", ["Son 1 Hafta", "Son 1 Ay", "Son 3 Ay", "Son 6 Ay", "Son 1 Yıl", "Tüm Zamanlar", "Özel Tarih"], index=5)
                
                limit_tarihi = None
                if zaman_filtresi != "Tüm Zamanlar":
                    if zaman_filtresi == "Son 1 Hafta": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=7))
                    elif zaman_filtresi == "Son 1 Ay": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=30))
                    elif zaman_filtresi == "Son 3 Ay": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=90))
                    elif zaman_filtresi == "Son 6 Ay": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=180))
                    elif zaman_filtresi == "Son 1 Yıl": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=365))
                    elif zaman_filtresi == "Özel Tarih":
                        col_t1, col_t2 = st.columns(2)
                        with col_t1: bas_tarih = st.date_input("Başlangıç Tarihi", df_gecmis["Tarih"].min().date(), format="DD/MM/YYYY")
                        with col_t2: bitis_tarih = st.date_input("Bitiş Tarihi", df_gecmis["Tarih"].max().date(), format="DD/MM/YYYY")
                        limit_tarihi = None
                        df_gecmis = df_gecmis[(df_gecmis["Tarih"].dt.date >= bas_tarih) & (df_gecmis["Tarih"].dt.date <= bitis_tarih)]
                    if limit_tarihi: df_gecmis = df_gecmis[df_gecmis["Tarih"] >= limit_tarihi]
                
                if len(df_gecmis) > 0:
                    y_secim = "Kâr/Zarar (%)" if grafik_turu1 == "Kâr/Zarar (%)" else "Güncel Değer (TL)"
                    cizilecek_y = [y_secim]
                    
                    secili_kiyaslar1 = list(kiyaslamalar1) + list(ozel_kiyas_hisse1)
                    
                    if secili_kiyaslar1:
                        df_kiyas = kiyas_verilerini_getir(tuple(ozel_kiyas_hisse1))
                        if not df_kiyas.empty:
                            df_gecmis["Tarih_Date"] = df_gecmis["Tarih"].dt.date
                            df_gecmis = pd.merge(df_gecmis, df_kiyas, left_on="Tarih_Date", right_on="Tarih", how="left").drop(columns=["Tarih_y", "Tarih_Date"]).rename(columns={"Tarih_x": "Tarih"})
                            
                            ilk_portfoy_val = df_gecmis[y_secim].iloc[0]
                            
                            for k_secim in secili_kiyaslar1:
                                if k_secim in df_gecmis.columns and not df_gecmis[k_secim].isna().all():
                                    df_gecmis[k_secim] = df_gecmis[k_secim].ffill().bfill()
                                    
                                    # Yahoo'dan çekilen veri yatay çizgiyse veya eksikse eklemeyi atla
                                    if len(df_gecmis) > 1 and df_gecmis[k_secim].nunique() <= 1:
                                        st.warning(f"⚠️ '{k_secim}' için Yahoo Finance üzerinde yeterli geçmiş veri bulunamadı. Grafiğe eklenemedi.")
                                        continue
                                        
                                    ilk_k = df_gecmis[k_secim].iloc[0]
                                    col_name = f"{k_secim} (Kıyas)"
                                    if y_secim == "Kâr/Zarar (%)": 
                                        df_gecmis[col_name] = ((df_gecmis[k_secim] - ilk_k) / ilk_k) * 100 + ilk_portfoy_val
                                    else: 
                                        df_gecmis[col_name] = (df_gecmis[k_secim] / ilk_k) * ilk_portfoy_val
                                    cizilecek_y.append(col_name)

                    fig_line = px.line(df_gecmis, x="Tarih", y=cizilecek_y, markers=True, labels={"value": y_secim, "variable": "Gösterge"})
                    fig_line.update_layout(xaxis_title="Tarih", yaxis_title=y_secim, hovermode="x unified")
                    st.plotly_chart(fig_line, use_container_width=True)

            st.markdown("---")
            with st.expander("📝 Geçmiş Kayıtları Yönet (Düzenle & Sil)", expanded=True):
                editor_data = []
                sorted_dates = sorted(gecmis_verisi.keys())
                prev_deg = None
                prev_h_deg = None
                
                for t in sorted_dates:
                    d = gecmis_verisi[t]
                    if hedef_anahtar in d:
                        yat = d[hedef_anahtar].get("yatirim", 0.0)
                        deg = d[hedef_anahtar].get("deger", 0.0)
                        
                        h_deg = d[hedef_anahtar].get("hisse_deger", 0.0) + d[hedef_anahtar].get("takas_deger", 0.0)
                        
                        kz_tl = deg - yat
                        kz_y = ((deg - yat) / yat * 100) if yat > 0 else 0
                        
                        if prev_deg is not None and prev_deg > 0:
                            g_fark_tl = deg - prev_deg
                            g_fark_y = (g_fark_tl / prev_deg) * 100
                        else:
                            g_fark_tl = 0.0
                            g_fark_y = 0.0
                            
                        if prev_h_deg is not None and prev_h_deg > 0:
                            g_h_fark_tl = h_deg - prev_h_deg
                            g_h_fark_y = (g_h_fark_tl / prev_h_deg) * 100
                        else:
                            g_h_fark_tl = 0.0
                            g_h_fark_y = 0.0
                            
                        editor_data.append({
                            "🗑️ Sil": False, "Tarih": t, "Yatırım (TL)": yat, "Güncel Değer (TL)": deg,
                            "Günlük Fark (TL)": g_fark_tl, "Günlük Fark (%)": g_fark_y,
                            "Hisse Günlük Fark (TL)": g_h_fark_tl, "Hisse Günlük Fark (%)": g_h_fark_y,
                            "Kâr/Zarar (TL)": kz_tl, "Kâr/Zarar (%)": kz_y
                        })
                        
                        prev_deg = deg
                        prev_h_deg = h_deg

                if editor_data:
                    df_editor = pd.DataFrame(editor_data).sort_values(by="Tarih", ascending=False).reset_index(drop=True)
                    df_editor["Tarih"] = pd.to_datetime(df_editor["Tarih"])
                    
                    edited_history = st.data_editor(
                        df_editor,
                        column_config={
                            "🗑️ Sil": st.column_config.CheckboxColumn("🗑️ Sil", default=False),
                            "Tarih": st.column_config.DateColumn("Tarih", format="DD.MM.YYYY", disabled=True),
                            "Yatırım (TL)": st.column_config.NumberColumn("Yatırım (TL)", min_value=0.0, format="%.2f ₺"),
                            "Güncel Değer (TL)": st.column_config.NumberColumn("Güncel Değer (TL)", min_value=0.0, format="%.2f ₺"),
                            "Günlük Fark (TL)": st.column_config.NumberColumn("Günlük Fark (TL)", format="%.2f ₺", disabled=True),
                            "Günlük Fark (%)": st.column_config.NumberColumn("Günlük Fark (%)", format="%% %.2f", disabled=True),
                            "Hisse Günlük Fark (TL)": st.column_config.NumberColumn("Hisse Günlük Fark (TL)", format="%.2f ₺", disabled=True),
                            "Hisse Günlük Fark (%)": st.column_config.NumberColumn("Hisse Günlük Fark (%)", format="%% %.2f", disabled=True),
                            "Kâr/Zarar (TL)": st.column_config.NumberColumn("Kâr/Zarar (TL)", format="%.2f ₺", disabled=True),
                            "Kâr/Zarar (%)": st.column_config.NumberColumn("Kâr/Zarar (%)", format="%% %.2f", disabled=True)
                        },
                        use_container_width=True, hide_index=True, key=f"hist_editor_genel"
                    )

                    if st.button("💾 Geçmişi Güncelle", type="primary", key="btn_hist_genel"):
                        degisiklik_var = False
                        for idx, row in edited_history.iterrows():
                            tarih_val = row["Tarih"]
                            if isinstance(tarih_val, str): tarih = tarih_val[:10]
                            else: tarih = tarih_val.strftime("%Y-%m-%d")
                                
                            if row["🗑️ Sil"]:
                                if hedef_anahtar in gecmis_verisi.get(tarih, {}):
                                    del gecmis_verisi[tarih][hedef_anahtar]
                                    if not gecmis_verisi[tarih]: del gecmis_verisi[tarih]
                                    degisiklik_var = True
                            else:
                                if tarih in gecmis_verisi and hedef_anahtar in gecmis_verisi[tarih]:
                                    yeni_yat = float(row["Yatırım (TL)"])
                                    yeni_deg = float(row["Güncel Değer (TL)"])
                                    eski_yat = gecmis_verisi[tarih][hedef_anahtar]["yatirim"]
                                    eski_deg = gecmis_verisi[tarih][hedef_anahtar]["deger"]

                                    if yeni_yat != eski_yat or yeni_deg != eski_deg:
                                        gecmis_verisi[tarih][hedef_anahtar]["yatirim"] = yeni_yat
                                        gecmis_verisi[tarih][hedef_anahtar]["deger"] = yeni_deg
                                        degisiklik_var = True

                        if degisiklik_var:
                            gecmis_kaydet(gecmis_verisi)
                            st.success("✅ Geçmiş kayıtlar güncellendi! Sayfa yenileniyor...")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.info("Değişiklik bulunamadı.")
                else:
                    st.info("Henüz geçmiş kayıt bulunmuyor.")

else:
    # TEKİL CÜZDAN GÖRÜNÜMÜ
    portfoy = portfoyler[secili_cuzdan]
    hatali_varliklar_tekil = set()

    c_bakiye = cuzdan_bakiyeler.get(secili_cuzdan, {"nakit": 0.0, "takas": 0.0})
    b_nkt = float(c_bakiye.get("nakit", 0.0))
    b_tks = float(c_bakiye.get("takas", 0.0))

    # --- 1. VERİLERİ ÖNCEDEN HESAPLAMA DÖNGÜSÜ ---
    tablo_verisi = []
    toplam_yatirim = 0
    toplam_guncel_deger = 0

    if b_nkt > 0:
        tablo_verisi.append({
            "Seç": False, "🗑️ Sil": False, "Durum": "⚪", "Tip": "Nakit", "Varlık": "Nakit Bakiye", "Sinyal": "➖ Nakit",
            "Alım Tarihi": None, "Gün": 0, "Günlük (%)": 0.0, "Lot": b_nkt, "Maliyet": 1.0, "Güncel Fiyat": 1.0,
            "Destek": 0.0, "Direnç": 0.0, "Hedef (%)": 0.0, "Stop (%)": 0.0,
            "Toplam Maliyet": b_nkt, "Güncel Değer": b_nkt, "K/Z (TL)": 0.0, "K/Z (%)": 0.0, 
            "Ort. Getiri (%)": 0.0, "Zirveye Uzaklık (%)": 0.0, "Zirve (Gün)": 0,
            "Teknik Skor": 0, "Temel Skor": 0
        })
    if b_tks > 0:
        tablo_verisi.append({
            "Seç": False, "🗑️ Sil": False, "Durum": "⚪", "Tip": "Nakit", "Varlık": "Takas Bakiye", "Sinyal": "➖ Takas",
            "Alım Tarihi": None, "Gün": 0, "Günlük (%)": 0.0, "Lot": b_tks, "Maliyet": 1.0, "Güncel Fiyat": 1.0,
            "Destek": 0.0, "Direnç": 0.0, "Hedef (%)": 0.0, "Stop (%)": 0.0,
            "Toplam Maliyet": b_tks, "Güncel Değer": b_tks, "K/Z (TL)": 0.0, "K/Z (%)": 0.0, 
            "Ort. Getiri (%)": 0.0, "Zirveye Uzaklık (%)": 0.0, "Zirve (Gün)": 0,
            "Teknik Skor": 0, "Temel Skor": 0
        })

    for hisse, detay in portfoy.items():
        maliyet, lot = float(detay["maliyet"]), float(detay["lot"])
        
        alim_str = detay.get("alim_tarihi", datetime.today().strftime("%Y-%m-%d"))
        try: alim_tarihi_obj = datetime.strptime(alim_str, "%Y-%m-%d").date()
        except: alim_tarihi_obj = datetime.today().date()
        
        try: elde_tutma_gunu = len(pd.bdate_range(start=alim_tarihi_obj, end=datetime.today().date()))
        except: elde_tutma_gunu = 0
        
        fiyat_bilgisi = fiyatlar_hepsi.get(hisse, {"guncel": 0.0, "onceki": maliyet, "destek":0, "direnc":0, "hedef_pot":0, "stop_marji":0, "sinyal":"➖", "teknik_skor": 0, "temel_skor": 0, "zirve_uzaklik_yuzde": 0.0, "zirve_gun": 0})
        
        guncel_fiyat = fiyat_bilgisi["guncel"]
        if guncel_fiyat <= 0: hatali_varliklar_tekil.add(hisse.replace('.IS', ''))
            
        onceki_fiyat = fiyat_bilgisi.get("onceki", maliyet)
        
        t_maliyet, g_deger = maliyet * lot, guncel_fiyat * lot
        kz_tl = g_deger - t_maliyet
        kz_yuzde = ((guncel_fiyat - maliyet) / maliyet * 100) if maliyet > 0 else 0
        
        toplam_yatirim += t_maliyet; toplam_guncel_deger += g_deger
        tip = "Hisse" if hisse.endswith(".IS") else "Fon"
        
        tablo_verisi.append({
            "Seç": False, "🗑️ Sil": False, "Durum": "🟢" if kz_tl > 0 else ("🔴" if kz_tl < 0 else "⚪"), "Tip": tip, "Varlık": hisse.replace(".IS", ""), "Sinyal": fiyat_bilgisi["sinyal"],
            "Alım Tarihi": alim_tarihi_obj, "Gün": elde_tutma_gunu,
            "Günlük (%)": ((guncel_fiyat - onceki_fiyat) / onceki_fiyat * 100) if onceki_fiyat > 0 else 0, "Lot": lot, 
            "Maliyet": round(maliyet, 2) if tip == "Hisse" else round(maliyet, 6), 
            "Güncel Fiyat": round(guncel_fiyat, 2) if tip == "Hisse" else round(guncel_fiyat, 6), 
            "Destek": round(fiyat_bilgisi["destek"], 2) if tip == "Hisse" else 0.0, 
            "Direnç": round(fiyat_bilgisi["direnc"], 2) if tip == "Hisse" else 0.0, 
            "Hedef (%)": fiyat_bilgisi["hedef_pot"], "Stop (%)": fiyat_bilgisi["stop_marji"],
            "Toplam Maliyet": t_maliyet, "Güncel Değer": g_deger, "K/Z (TL)": kz_tl, "K/Z (%)": kz_yuzde,
            "Ort. Getiri (%)": (kz_yuzde / elde_tutma_gunu) if elde_tutma_gunu > 0 else kz_yuzde,
            "Zirveye Uzaklık (%)": fiyat_bilgisi.get("zirve_uzaklik_yuzde", 0.0),
            "Zirve (Gün)": fiyat_bilgisi.get("zirve_gun", 0),
            "Teknik Skor": fiyat_bilgisi["teknik_skor"], "Temel Skor": fiyat_bilgisi["temel_skor"]
        })

    genel_kz_tl = toplam_guncel_deger - toplam_yatirim
    genel_kz_yuzde = ((toplam_guncel_deger - toplam_yatirim) / toplam_yatirim * 100) if toplam_yatirim > 0 else 0

    if hatali_varliklar_tekil:
        st.error(f"⚠️ **DİKKAT:** Aşağıdaki varlıkların fiyatı bağlantı sorunu nedeniyle çekilemedi (0 TL olarak görünüyor): **{', '.join(list(hatali_varliklar_tekil))}**. Lütfen yukarıdaki '🔄 Yeniden Hesapla' butonuna basarak tekrar deneyin.")

    # --- 2. EN ÜSTTE METRİKLERİN GÖSTERİMİ ---
    st.markdown("<h4 style='margin-bottom:0;'>📊 Güncel Durum</h4>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Toplam Yatırım", f"{tr_format(toplam_yatirim)} ₺")
    m2.metric("📈 Güncel Portföy", f"{tr_format(toplam_guncel_deger)} ₺")
    m3.metric("💸 Kâr/Zarar (TL)", f"{tr_format(genel_kz_tl)} ₺", delta_color="normal" if genel_kz_tl >= 0 else "inverse")
    yuzde_str = f"% {tr_format(genel_kz_yuzde)}"
    m4.metric("📊 Kâr/Zarar (%)", yuzde_str, delta=yuzde_str if genel_kz_yuzde >= 0 else yuzde_str, delta_color="normal" if genel_kz_yuzde >= 0 else "inverse")
    
    st.markdown("<br>", unsafe_allow_html=True)
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("💵 Cüzdan Nakit", f"{tr_format(b_nkt)} ₺")
    n2.metric("⏳ Cüzdan Takas", f"{tr_format(b_tks)} ₺")
    
    st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)

    # --- 3. NAKİT/TAKAS DÜZENLEME PANELİ ---
    with st.expander(f"💵 '{secili_cuzdan}' Nakit ve Takas Bakiyesi Düzenle", expanded=False):
        col_n, col_t, col_btn = st.columns([1.5, 1.5, 1.5])
        with col_n: y_nkt = st.number_input("Cüzdan Nakit (TL):", value=b_nkt, step=100.0, format="%.2f")
        with col_t: y_tks = st.number_input("Cüzdan Takas (TL):", value=b_tks, step=100.0, format="%.2f")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Bakiyeyi Güncelle", type="primary", use_container_width=True):
                cuzdan_bakiyeler[secili_cuzdan] = {"nakit": y_nkt, "takas": y_tks}
                bakiyeler_kaydet(cuzdan_bakiyeler)
                st.rerun()

    # --- 4. YENİ VARLIK EKLE PANELİ ---
    with st.expander(f"➕ '{secili_cuzdan}' Cüzdanına Yeni Varlık Ekle", expanded=True):
        varlik_turu = st.radio("Eklenecek Varlık Türü:", ["📈 Hisse Senedi (BIST)", "🏦 Yatırım Fonu (TEFAS)"], horizontal=True)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            yeni_varlik = st.text_input("Hisse Kodu:" if "Hisse" in varlik_turu else "Fon Kodu:").upper().strip()
        with c2:
            yeni_lot = st.number_input("Adet:", min_value=0.0, format="%.0f", step=1.0)
        with c3:
            yeni_alim_tarihi = st.date_input("Alım Tarihi", value=datetime.today())
        with c4:
            giris_yontemi = st.selectbox("Maliyet Girişi:", ["💵 Maliyeti Biliyorum", "🏦 Bankadaki Kâr/Zararı Biliyorum"])
        
        st.markdown("---")
        col_m1, col_m2 = st.columns([2, 1])
        if "Maliyeti" in giris_yontemi:
            with col_m1: yeni_maliyet = st.number_input("Ortalama Maliyet (TL):", min_value=0.0, format="%.6f", step=0.01)
            with col_m2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Varlığı Kaydet", type="primary", use_container_width=True):
                    if yeni_varlik and yeni_maliyet > 0 and yeni_lot > 0:
                        kod = yeni_varlik if ("Hisse" in varlik_turu and not yeni_varlik.endswith(".IS")) else yeni_varlik
                        if "Hisse" in varlik_turu and not kod.endswith(".IS"): kod += ".IS"
                        portfoyler[secili_cuzdan][kod] = {"maliyet": float(yeni_maliyet), "lot": float(yeni_lot), "alim_tarihi": yeni_alim_tarihi.strftime("%Y-%m-%d")}
                        portfoy_kaydet(portfoyler)
                        
                        if "Hisse" in varlik_turu:
                            fav_kodu = kod.replace(".IS", "")
                            fav_veri = favorileri_getir()
                            if isinstance(fav_veri, list):
                                fav_veri = {k: {"takipte": False, "maliyet": 0.0} for k in fav_veri}
                            fav_veri[fav_kodu] = {"takipte": True, "maliyet": float(yeni_maliyet)}
                            favorileri_kaydet(fav_veri)
                        
                        st.rerun()
        else:
            with col_m1: banka_kar = st.number_input("Bankada Görünen Toplam Kâr / Zarar (TL):", format="%.2f")
            with col_m2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Hesapla ve Kaydet", type="primary", use_container_width=True):
                    if yeni_varlik and yeni_lot > 0:
                        kod = yeni_varlik if ("Hisse" in varlik_turu and not yeni_varlik.endswith(".IS")) else yeni_varlik
                        if "Hisse" in varlik_turu and not kod.endswith(".IS"): kod += ".IS"
                        with st.spinner("Anlık fiyat çekiliyor..."):
                            if "Hisse" in varlik_turu:
                                try: guncel_f = float(yf.download(kod, period="1d", progress=False)['Close'].iloc[-1])
                                except: guncel_f = 0.0
                            else: guncel_f = font_fiyati_getir_canli(kod)
                        
                        if guncel_f > 0:
                            hesaplanan_birim_maliyet = ((guncel_f * yeni_lot) - banka_kar) / yeni_lot
                            portfoyler[secili_cuzdan][kod] = {"maliyet": float(hesaplanan_birim_maliyet), "lot": float(yeni_lot), "alim_tarihi": yeni_alim_tarihi.strftime("%Y-%m-%d")}
                            portfoy_kaydet(portfoyler)
                            
                            if "Hisse" in varlik_turu:
                                fav_kodu = kod.replace(".IS", "")
                                fav_veri = favorileri_getir()
                                if isinstance(fav_veri, list):
                                    fav_veri = {k: {"takipte": False, "maliyet": 0.0} for k in fav_veri}
                                fav_veri[fav_kodu] = {"takipte": True, "maliyet": float(hesaplanan_birim_maliyet)}
                                favorileri_kaydet(fav_veri)
                                
                            st.rerun()

    # --- 5. DATAFRAME OLUŞTURMA VE SÜTUN GİZLE/GÖSTER PANELİ ---
    df_portfoy = pd.DataFrame(tablo_verisi)
    
    if not df_portfoy.empty:
        sinyal_sutunu_aktif = st.session_state.get("sinyal_goster", False)
        tum_olasi_sutunlar = [c for c in df_portfoy.columns if c not in ["Seç", "🗑️ Sil", "#"]]
        
        if not sinyal_sutunu_aktif:
            sinyal_kolonlari = ["Sinyal", "Destek", "Direnç", "Hedef (%)", "Stop (%)", "Teknik Skor", "Temel Skor"]
            tum_olasi_sutunlar = [c for c in tum_olasi_sutunlar if c not in sinyal_kolonlari]

        if not st.session_state.get("zirve_hesap_kutusu", False):
            if "Zirveye Uzaklık (%)" in tum_olasi_sutunlar: tum_olasi_sutunlar.remove("Zirveye Uzaklık (%)")
            if "Zirve (Gün)" in tum_olasi_sutunlar: tum_olasi_sutunlar.remove("Zirve (Gün)")

        if not st.session_state.get("p_temel", False) and "Temel Skor" in tum_olasi_sutunlar:
            tum_olasi_sutunlar.remove("Temel Skor")
        if not st.session_state.get("p_tek", True) and "Teknik Skor" in tum_olasi_sutunlar:
            tum_olasi_sutunlar.remove("Teknik Skor")

        kayitli_sutun_ayarlari = portfoy_sutun_ayarlari_getir()
        for s in tum_olasi_sutunlar:
            chk_key = f"pchk_{s}"
            if chk_key not in st.session_state:
                varsayilan_gizli = ["Destek", "Direnç", "Hedef (%)", "Stop (%)"]
                if chk_key in kayitli_sutun_ayarlari:
                    st.session_state[chk_key] = kayitli_sutun_ayarlari[chk_key]
                else:
                    st.session_state[chk_key] = s not in varsayilan_gizli

        with st.expander("👁️ Sütunları Gizle / Göster Paneli", expanded=False):
            st.markdown("Tabloda görmek istediğiniz sütunları seçin:")
            cb_s1, cb_s2 = st.columns(2)
            if cb_s1.button("✅ Tümünü Göster", key="show_all_cols_mod2"):
                for s in tum_olasi_sutunlar: st.session_state[f"pchk_{s}"] = True
                portfoy_sutun_degisti(); st.rerun()
            if cb_s2.button("❌ Tümünü Gizle", key="hide_all_cols_mod2"):
                for s in tum_olasi_sutunlar: 
                    if s not in ["Varlık", "Durum", "Tip"]: st.session_state[f"pchk_{s}"] = False
                portfoy_sutun_degisti(); st.rerun()

            st.markdown("---")
            grid = st.columns(6)
            for i, s in enumerate(tum_olasi_sutunlar):
                grid[i % 6].checkbox(s, key=f"pchk_{s}", on_change=portfoy_sutun_degisti)

        sec_cols = [s for s in tum_olasi_sutunlar if st.session_state.get(f"pchk_{s}", True)]
        
        saga_alinacaklar = ["Teknik Skor", "Temel Skor", "Sinyal"]
        for col in saga_alinacaklar:
            if col in sec_cols:
                sec_cols.remove(col)
                sec_cols.append(col)

        # --- 6. ARAMA VE FİLTRELEME ARAÇLARI (YAN YANA HİZALI) ---
        st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
        c_ara, c_sira, c_sinyal, c_btn = st.columns([2, 2, 2, 1])
        with c_ara:
            st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>Varlık Ara:</p>", unsafe_allow_html=True)
            ara = st.text_input("Ara", key="arama_kutusu", placeholder="🔍 Varlık Ara...", label_visibility="collapsed").upper()
        with c_sira:
            st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>Sırala:</p>", unsafe_allow_html=True)
            siralama_secimi = st.selectbox(
                "Sırala",
                ["🔤 A'dan Z'ye (Varlık Adı)", "🔤 Z'den A'ya (Varlık Adı)", "💰 Güncel Değer (Yüksekten Düşüğe)", "🎯 Teknik Puana Göre", "🚦 Sinyale Göre", "📈 En Çok Kâr Edenler (%)", "📉 En Çok Zarar Edenler (%)", "🔥 Günlük Kazandıranlar (%)"],
                index=0, label_visibility="collapsed"
            )
        with c_sinyal:
            st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>Sinyale Göre Filtrele:</p>", unsafe_allow_html=True)
            secili_sinyaller = st.multiselect("Sinyal", ["⚡ GÜÇLÜ AL (KV)", "🛡️ GÜÇLÜ AL (OV)", "🚀 GÜÇLÜ AL", "🌱 KADEMELİ", "⏳ BEKLE", "⚠️ KÂR AL", "⛔ SAT"], key="sinyal_filtre_kutusu", label_visibility="collapsed", placeholder="🚦 Sinyale Göre...")
        with c_btn:
            st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px;'>&nbsp;</p>", unsafe_allow_html=True)
            st.button("🔄 Sıfırla", on_click=filtreleri_sifirla, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # --- 7. TABLO KONTROL BUTONLARI ---
        st.markdown("### 📈 Hisse Senetleri")
        if f"master_sec_hisse_{secili_cuzdan}" not in st.session_state: st.session_state[f"master_sec_hisse_{secili_cuzdan}"] = False

        c_sh1, c_sh2, c_sh3, c_sh4, c_sh5 = st.columns([1.5, 1.5, 2.5, 1.5, 1.5])
        with c_sh1:
            if st.button("☑️ Tümünü Seç", key=f"btn_sec_hisse_{secili_cuzdan}"):
                st.session_state[f"master_sec_hisse_{secili_cuzdan}"] = True
                if "ed_hisse" in st.session_state: del st.session_state["ed_hisse"]
                st.rerun()
        with c_sh2:
            if st.button("🔲 Seçimi Kaldır", key=f"btn_kaldir_hisse_{secili_cuzdan}"):
                st.session_state[f"master_sec_hisse_{secili_cuzdan}"] = False
                if "ed_hisse" in st.session_state: del st.session_state["ed_hisse"]
                st.rerun()
        with c_sh3:
            st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
            takasa_ekle_secimi = st.checkbox("💰 Silinenleri Takasa Ekle", value=False, key=f"takasa_ekle_{secili_cuzdan}")
        with c_sh4:
            st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
            sadece_favoriler = st.checkbox("⭐ Sadece Favori", key="sadece_fav_kutusu")
        with c_sh5:
            st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
            tumunu_goster_m2 = st.toggle("Tüm Varlıklar", value=True)

        # --- 8. FİLTRELERİN UYGULANMASI ---
        df_f = df_portfoy.copy()
        
        if not tumunu_goster_m2: df_f = df_f[df_f["Tip"] == "Hisse"]
        if ara: df_f = df_f[df_f['Varlık'].str.contains(ara, na=False)]
        
        fav_liste = favorileri_getir()
        fav_keys = list(fav_liste.keys()) if isinstance(fav_liste, dict) else fav_liste
        if sadece_favoriler: df_f = df_f[df_f['Varlık'].isin(fav_keys)]
        if secili_sinyaller: df_f = df_f[df_f['Sinyal'].isin(secili_sinyaller)]
            
        if "A'dan Z'ye" in siralama_secimi: df_f = df_f.sort_values(by="Varlık", ascending=True)
        elif "Z'den A'ya" in siralama_secimi: df_f = df_f.sort_values(by="Varlık", ascending=False)
        elif "Güncel Değer" in siralama_secimi: df_f = df_f.sort_values(by="Güncel Değer", ascending=False)
        elif "Teknik Puan" in siralama_secimi: df_f = df_f.sort_values(by="Teknik Skor", ascending=False)
        elif "Sinyale Göre" in siralama_secimi:
            sinyal_sira = {"⚡ GÜÇLÜ AL (KV)": 1, "🛡️ GÜÇLÜ AL (OV)": 2, "🚀 GÜÇLÜ AL": 3, "🌱 KADEMELİ": 4, "⏳ BEKLE": 5, "⚠️ KÂR AL": 6, "⛔ SAT": 7}
            df_f['Sinyal_Sira'] = df_f['Sinyal'].map(lambda x: sinyal_sira.get(x, 99))
            df_f = df_f.sort_values(by=["Sinyal_Sira", "Güncel Değer"], ascending=[True, False]).drop(columns=['Sinyal_Sira'])
        elif "En Çok Kâr" in siralama_secimi: df_f = df_f.sort_values(by="K/Z (%)", ascending=False)
        elif "En Çok Zarar" in siralama_secimi: df_f = df_f.sort_values(by="K/Z (%)", ascending=True)
        elif "Günlük Kazandıranlar" in siralama_secimi: df_f = df_f.sort_values(by="Günlük (%)", ascending=False)

        df_f = df_f.reset_index(drop=True)
        df_f.insert(1, "#", range(1, len(df_f) + 1))
        
        # --- 9. TABLOLARIN ÇİZİMİ (DATAFRAME RENDER) ---
        gosterilecek_sutunlar = [c for c in ["Seç", "🗑️ Sil", "#"] if c in df_f.columns] + sec_cols
        df_gosterim_tekil = df_f[gosterilecek_sutunlar].copy()

        if "Teknik Skor" in df_gosterim_tekil.columns: df_gosterim_tekil["Teknik Skor"] = pd.to_numeric(df_gosterim_tekil["Teknik Skor"], errors='coerce').fillna(0).astype(int)
        if "Temel Skor" in df_gosterim_tekil.columns: df_gosterim_tekil["Temel Skor"] = pd.to_numeric(df_gosterim_tekil["Temel Skor"], errors='coerce').fillna(0).astype(int)

        col_conf_tekil = {
            "Seç": st.column_config.CheckboxColumn("Seç", default=False, width=40),
            "🗑️ Sil": st.column_config.CheckboxColumn("🗑️ Sil", default=False, width=45),
            "#": st.column_config.NumberColumn("#", format="%d", disabled=True, width=30),
            "Durum": st.column_config.TextColumn("Durum", disabled=True, width=50),
            "Tip": st.column_config.TextColumn("Tip", disabled=True, width=80),
            "Varlık": st.column_config.TextColumn("Varlık", disabled=True, width=70),
            "Alım Tarihi": st.column_config.DateColumn("Alım", format="DD.MM.YYYY", width=80),
            "Gün": st.column_config.NumberColumn("Gün", disabled=True, width=40),
            "Günlük (%)": st.column_config.NumberColumn("Günlük (%)", format="%% %,.2f", disabled=True, width=75),
            "Lot": st.column_config.NumberColumn("Lot", min_value=0.0, format=None, width=44),
            "Maliyet": st.column_config.NumberColumn("Maliyet", min_value=0.0, format=None, width=58), 
            "Güncel Fiyat": st.column_config.NumberColumn("Fiyat", format=None, disabled=True, width=58), 
            "Toplam Maliyet": st.column_config.NumberColumn("Toplam Maliyet", format="%,.2f ₺", disabled=True, width=100),
            "Güncel Değer": st.column_config.NumberColumn("Güncel Değer", format="%,.2f ₺", disabled=True, width=100),
            "K/Z (TL)": st.column_config.NumberColumn("K/Z (TL)", format="%,.2f ₺", disabled=True, width=100),
            "K/Z (%)": st.column_config.NumberColumn("K/Z (%)", format="%% %,.2f", disabled=True, width=72),
            "Ort. Getiri (%)": st.column_config.NumberColumn("Ort. Getiri (%)", format="%% %,.2f", disabled=True, width=80),
            "Sinyal": st.column_config.TextColumn("Sinyal", disabled=True, width=90),
            "Destek": st.column_config.NumberColumn("Destek", format=None, disabled=True, width=65),
            "Direnç": st.column_config.NumberColumn("Direnç", format=None, disabled=True, width=65),
            "Hedef (%)": st.column_config.NumberColumn("Hedef (%)", format="%% %,.2f", disabled=True, width=70),
            "Stop (%)": st.column_config.NumberColumn("Stop (%)", format="%% %,.2f", disabled=True, width=70),
            "Zirveye Uzaklık (%)": st.column_config.NumberColumn("Zirveye Uzaklık (%)", format="%% %,.2f", disabled=True, width=90),
            "Zirve (Gün)": st.column_config.NumberColumn("Zirve (Gün)", format="%d", disabled=True, width=70)
        }
        if "Teknik Skor" in sec_cols: col_conf_tekil["Teknik Skor"] = st.column_config.ProgressColumn("Teknik Puan", format="%d", min_value=0, max_value=100, width=117)
        if "Temel Skor" in sec_cols: col_conf_tekil["Temel Skor"] = st.column_config.ProgressColumn("Temel Kalite", format="%d", min_value=0, max_value=100, width="medium")

        df_hisse = df_gosterim_tekil[df_f["Tip"] == "Hisse"].reset_index(drop=True)
        df_fon = df_gosterim_tekil[df_f["Tip"] == "Fon"].reset_index(drop=True)
        
        edited_hisse, edited_fon = None, None
        
        if not df_hisse.empty:
            df_hisse["Seç"] = st.session_state[f"master_sec_hisse_{secili_cuzdan}"]

            h_yuks = max(200, int((len(df_hisse) + 1) * 36 + 40))
            edited_hisse = st.data_editor(df_hisse, column_config=col_conf_tekil, use_container_width=True, hide_index=True, height=h_yuks, key="ed_hisse")
            
            secilen_h = edited_hisse[edited_hisse["Seç"] == True]
            if not secilen_h.empty:
                s_yat_h = secilen_h["Toplam Maliyet"].sum()
                s_deg_h = secilen_h["Güncel Değer"].sum()
                s_kz_h = s_deg_h - s_yat_h
                s_kzy_h = (s_kz_h / s_yat_h * 100) if s_yat_h > 0 else 0
                st.success(f"🎯 **SEÇİLİ HİSSELER TOPLAMI:** Toplam Maliyet: **{tr_format(s_yat_h)} ₺** | Güncel Değer: **{tr_format(s_deg_h)} ₺** | K/Z: **{tr_format(s_kz_h)} ₺** (% {tr_format(s_kzy_h)})")

        if not df_fon.empty:
            st.markdown("### 🏦 Yatırım Fonları")
            if f"master_sec_fon_{secili_cuzdan}" not in st.session_state: st.session_state[f"master_sec_fon_{secili_cuzdan}"] = False

            c_sf1, c_sf2, _ = st.columns([1.5, 1.5, 7])
            with c_sf1:
                if st.button("☑️ Tümünü Seç", key=f"btn_sec_fon_{secili_cuzdan}"):
                    st.session_state[f"master_sec_fon_{secili_cuzdan}"] = True
                    if "ed_fon" in st.session_state: del st.session_state["ed_fon"]
                    st.rerun()
            with c_sf2:
                if st.button("🔲 Seçimi Kaldır", key=f"btn_kaldir_fon_{secili_cuzdan}"):
                    st.session_state[f"master_sec_fon_{secili_cuzdan}"] = False
                    if "ed_fon" in st.session_state: del st.session_state["ed_fon"]
                    st.rerun()

            df_fon["Seç"] = st.session_state[f"master_sec_fon_{secili_cuzdan}"]

            f_yuks = max(200, int((len(df_fon) + 1) * 36 + 40))
            edited_fon = st.data_editor(df_fon, column_config=col_conf_tekil, use_container_width=True, hide_index=True, height=f_yuks, key="ed_fon")
            
            secilen_f = edited_fon[edited_fon["Seç"] == True]
            if not secilen_f.empty:
                s_yat_f = secilen_f["Toplam Maliyet"].sum()
                s_deg_f = secilen_f["Güncel Değer"].sum()
                s_kz_f = s_deg_f - s_yat_f
                s_kzy_f = (s_kz_f / s_yat_f * 100) if s_yat_f > 0 else 0
                st.success(f"🎯 **SEÇİLİ FONLAR TOPLAMI:** Toplam Maliyet: **{tr_format(s_yat_f)} ₺** | Güncel Değer: **{tr_format(s_deg_f)} ₺** | K/Z: **{tr_format(s_kz_f)} ₺** (% {tr_format(s_kzy_f)})")

        if st.button("💾 Tablodaki Değişiklikleri Kaydet (Sil / Düzenle)", type="primary", use_container_width=True):
            yeni_portfoy_verisi = portfoyler[secili_cuzdan].copy()
            degisiklik_yapildi = False
            islem_gecmisine_eklendi = False
            c_ig = islem_gecmisi.get(secili_cuzdan, [])
            
            toplam_takasa_eklenecek = 0.0
            
            tum_satirlar = []
            if edited_hisse is not None: tum_satirlar.extend(edited_hisse.to_dict('records'))
            if edited_fon is not None: tum_satirlar.extend(edited_fon.to_dict('records'))
            
            for idx, row in enumerate(tum_satirlar):
                alim_v = row.get("Alım Tarihi")
                if pd.isna(alim_v) or alim_v is None:
                    alim_s = datetime.today().strftime("%Y-%m-%d")
                elif isinstance(alim_v, str):
                    alim_s = alim_v[:10]
                else:
                    alim_s = alim_v.strftime("%Y-%m-%d")
                    
                varlik_adi = str(row["Varlık"]).strip()
                is_hisse = str(row.get("Tip", "")) == "Hisse"
                
                kod = varlik_adi + ".IS" if is_hisse and not varlik_adi.endswith(".IS") else varlik_adi
                
                if kod not in yeni_portfoy_verisi and varlik_adi + ".IS" in yeni_portfoy_verisi:
                    kod = varlik_adi + ".IS"
                    
                if not row.get("🗑️ Sil", False):
                    if kod in yeni_portfoy_verisi:
                        eski_mal = float(yeni_portfoy_verisi[kod]["maliyet"])
                        eski_lot = float(yeni_portfoy_verisi[kod]["lot"])
                        eski_tarih = yeni_portfoy_verisi[kod].get("alim_tarihi", "")
                        
                        y_mal = float(row["Maliyet"])
                        y_lot = float(row["Lot"])
                        
                        if eski_mal != y_mal or eski_lot != y_lot or eski_tarih != alim_s:
                            yeni_portfoy_verisi[kod] = {"maliyet": y_mal, "lot": y_lot, "alim_tarihi": alim_s}
                            degisiklik_yapildi = True
                else: 
                    if kod in yeni_portfoy_verisi:
                        del yeni_portfoy_verisi[kod]
                        degisiklik_yapildi = True 
                    
                    m_fiyat = float(row["Maliyet"])
                    s_lot = float(row["Lot"])
                    s_fiyat = float(row.get("Güncel Fiyat", m_fiyat))
                    k_z = (s_fiyat - m_fiyat) * s_lot
                    k_z_y = ((s_fiyat - m_fiyat) / m_fiyat) * 100 if m_fiyat > 0 else 0
                    satis_tutari = s_lot * s_fiyat
                    
                    if st.session_state.get(f"takasa_ekle_{secili_cuzdan}", False):
                        toplam_takasa_eklenecek += satis_tutari
                    
                    yeni_id = str(int(time.time()*1000) + idx)
                    c_ig.append({
                        "id": yeni_id,
                        "Alım Tarihi": alim_s,
                        "Tarih": datetime.today().strftime("%Y-%m-%d"),
                        "Tip": "Satım",
                        "Varlık": varlik_adi.replace(".IS", ""),
                        "Lot": s_lot,
                        "Fiyat": s_fiyat,
                        "Maliyet": m_fiyat,
                        "Kâr/Zarar (TL)": k_z,
                        "Kâr/Zarar (%)": k_z_y
                    })
                    islem_gecmisine_eklendi = True
                    
            if islem_gecmisine_eklendi:
                islem_gecmisi[secili_cuzdan] = c_ig
                islem_gecmisi_kaydet(islem_gecmisi)
                    
            if toplam_takasa_eklenecek > 0:
                if secili_cuzdan not in cuzdan_bakiyeler:
                    cuzdan_bakiyeler[secili_cuzdan] = {"nakit": 0.0, "takas": 0.0}
                cuzdan_bakiyeler[secili_cuzdan]["takas"] = float(cuzdan_bakiyeler[secili_cuzdan].get("takas", 0.0)) + toplam_takasa_eklenecek
                bakiyeler_kaydet(cuzdan_bakiyeler)
                    
            if degisiklik_yapildi or toplam_takasa_eklenecek > 0:
                portfoyler[secili_cuzdan] = yeni_portfoy_verisi
                portfoy_kaydet(portfoyler)
                st.rerun()

        col_grafik, col_hesap = st.columns([1, 1.2])
        with col_grafik:
            if len(df_portfoy) > 0 and toplam_guncel_deger > 0:
                st.markdown("---"); st.subheader("🥧 Portföy Dağılımı")
                fig = px.pie(df_portfoy, values='Güncel Değer', names='Varlık', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                fig.update_traces(textposition='inside', textinfo='percent+label'); fig.update_layout(margin=dict(t=20, b=0, l=0, r=0), height=350)
                st.plotly_chart(fig, use_container_width=True)

        with col_hesap:
            st.markdown("---"); st.subheader("📉 Maliyet Düşürme Hesaplayıcısı")
            if len(df_f) > 0:
                hisse_sec = st.selectbox("Hesaplama Yapılacak Varlık:", df_f['Varlık'].tolist(), key="calc_sel_m2")
                if hisse_sec:
                    secili_veri = df_f[df_f['Varlık'] == hisse_sec].iloc[0]
                    
                    if secili_veri['Tip'] != "Nakit":
                        m_toplam_maliyet = float(secili_veri.get('Toplam Maliyet', secili_veri.get('Toplam Yatırım', 0)))
                        m_lot = float(secili_veri['Lot'])
                        m_maliyet = m_toplam_maliyet / m_lot if m_lot > 0 else float(secili_veri['Maliyet'])
                        g_fiyat = float(secili_veri['Güncel Fiyat'])
                        is_hisse = "Hisse" in str(secili_veri['Tip'])
                        
                        st.info(f"📌 **Mevcut Durum:** **{tr_format(m_lot, 0 if is_hisse else 3)}** Adet | Maliyet: **{tr_format(m_maliyet, 6)} ₺** | Güncel: **{tr_format(g_fiyat, 6)} ₺**")
                        secim_hesap = st.radio("Hesaplama Yöntemini Seçin:", ["💵 Tutara Göre (TL)", "📦 Adete Göre"], horizontal=True, key=f"calc_rad_m2_{hisse_sec}")
                        c_alim1, c_alim2 = st.columns(2)
                        
                        if "Tutara" in secim_hesap:
                            with c_alim1: yeni_fiyat = st.number_input("Alım Fiyatı (TL):", value=g_fiyat, step=0.10, format="%.6f", key=f"fiyat1_m2_{hisse_sec}")
                            with c_alim2:
                                ek_butce_input = st.number_input("Yatırılacak Ek Para (TL):", min_value=0.0, value=0.0, step=1000.0, format="%.2f", key=f"butce_m2_{hisse_sec}")
                            if yeni_fiyat > 0:
                                yeni_lot = ek_butce_input / yeni_fiyat
                                if is_hisse: yeni_lot = int(yeni_lot)
                                ek_butce = yeni_lot * yeni_fiyat
                            else:
                                yeni_lot = 0; ek_butce = 0
                        else:
                            with c_alim1: yeni_fiyat = st.number_input("Alım Fiyatı (TL):", value=g_fiyat, step=0.10, format="%.6f", key=f"fiyat2_m2_{hisse_sec}")
                            with c_alim2:
                                yeni_lot_input = st.number_input("Alınacak Ek Adet:", min_value=0.0, value=0.0, step=100.0 if is_hisse else 1000.0, format="%.0f" if is_hisse else "%.3f", key=f"lot_m2_{hisse_sec}")
                            yeni_lot = int(yeni_lot_input) if is_hisse else float(yeni_lot_input)
                            ek_butce = yeni_fiyat * yeni_lot
                        
                        if yeni_lot > 0 or ek_butce > 0:
                            yeni_toplam_lot = m_lot + yeni_lot
                            yeni_toplam_maliyet = m_toplam_maliyet + ek_butce
                            yeni_ortalama = yeni_toplam_maliyet / yeni_toplam_lot if yeni_toplam_lot > 0 else 0
                            fark_tl = m_maliyet - yeni_ortalama
                            yeni_kz_tl = (yeni_fiyat * yeni_toplam_lot) - yeni_toplam_maliyet
                            yeni_kz_yuzde = ((yeni_fiyat - yeni_ortalama) / yeni_ortalama) * 100 if yeni_ortalama > 0 else 0
                            kz_ikon = "🟢" if yeni_kz_tl > 0 else ("🔴" if yeni_kz_tl < 0 else "⚪")
                            st.success(f"🎯 **YENİ ORTALAMANIZ:** {tr_format(yeni_ortalama, 6)} ₺\n\n📉 Maliyetiniz **{tr_format(fark_tl, 6)} ₺** düşecek!\n\n---\n{kz_ikon} **Olası Yeni Kâr/Zarar (Alım Fiyatına Göre):** {tr_format(yeni_kz_tl)} ₺ (% {tr_format(yeni_kz_yuzde)})")
            else:
                st.info("Nakit ve Takas bakiyeleri için maliyet düşürme hesabı yapılamaz.")

        st.markdown("---")
        with st.expander(f"📜 '{secili_cuzdan}' İşlem Geçmişi ve Gerçekleşen Kâr/Zarar", expanded=False):
            c_ig_veri = islem_gecmisi.get(secili_cuzdan, [])
            
            st.markdown("#### ➕ Yeni İşlem Ekle")
            with st.form("form_islem_ekle"):
                c_f1, c_f2, c_f3, c_f4, c_f5, c_f6 = st.columns(6)
                with c_f1: form_alim_tarihi = st.date_input("Alım Tarihi", datetime.today() - timedelta(days=1))
                with c_f2: form_tarih = st.date_input("Satım Tarihi", datetime.today())
                with c_f3: form_varlik = st.text_input("Varlık Kodu (Örn: THYAO)").upper().strip()
                with c_f4: form_lot = st.number_input("Adet (Lot)", min_value=0.01, value=100.0, step=1.0)
                with c_f5: form_fiyat = st.number_input("Satış Fiyatı (TL)", min_value=0.0, format="%.4f", step=0.1)
                with c_f6: form_maliyet = st.number_input("Maliyet Fiyatı (TL)", min_value=0.0, format="%.4f", step=0.1)
                
                submit_islem = st.form_submit_button("Satım İşlemini Günlüğe Kaydet")
                
                if submit_islem and form_varlik and form_lot > 0 and form_fiyat > 0:
                    kz_tl = 0.0
                    kz_yuzde = 0.0
                    if form_maliyet > 0:
                        kz_tl = (form_fiyat - form_maliyet) * form_lot
                        kz_yuzde = ((form_fiyat - form_maliyet) / form_maliyet) * 100
                    
                    yeni_islem = {
                        "id": str(int(time.time()*1000)),
                        "Alım Tarihi": form_alim_tarihi.strftime("%Y-%m-%d"),
                        "Tarih": form_tarih.strftime("%Y-%m-%d"),
                        "Tip": "Satım",
                        "Varlık": form_varlik,
                        "Lot": form_lot,
                        "Fiyat": form_fiyat,
                        "Maliyet": form_maliyet,
                        "Kâr/Zarar (TL)": kz_tl,
                        "Kâr/Zarar (%)": kz_yuzde
                    }
                    c_ig_veri.append(yeni_islem)
                    islem_gecmisi[secili_cuzdan] = c_ig_veri
                    islem_gecmisi_kaydet(islem_gecmisi)
                    st.rerun()

            toplam_gerceklesen_kz = sum(item.get("Kâr/Zarar (TL)", 0) for item in c_ig_veri if item.get("Tip", "Satım") == "Satım")
            st.markdown(f"**💰 Toplam Gerçekleşen Kâr/Zarar:** <span style='color:{'green' if toplam_gerceklesen_kz >= 0 else 'red'}'>{tr_format(toplam_gerceklesen_kz)} ₺</span>", unsafe_allow_html=True)

            ig_ara = st.text_input("🔍 Varlık Adına Göre Filtrele (İşlem Geçmişi):", key=f"ig_ara_{secili_cuzdan}").upper()

            if c_ig_veri:
                df_ig = pd.DataFrame(c_ig_veri)
                if ig_ara:
                    df_ig = df_ig[df_ig['Varlık'].str.contains(ig_ara, na=False)]
                
                if "Alım Tarihi" not in df_ig.columns:
                    df_ig["Alım Tarihi"] = df_ig["Tarih"]
                
                df_ig["Satış Tutarı (TL)"] = df_ig["Lot"] * df_ig["Fiyat"]
                try:
                    df_ig["Gün"] = (pd.to_datetime(df_ig["Tarih"]) - pd.to_datetime(df_ig["Alım Tarihi"])).dt.days
                except:
                    df_ig["Gün"] = 0
                
                def fiyat_getir_gecmis(v_adi):
                    if v_adi + ".IS" in fiyatlar_hepsi: return fiyatlar_hepsi[v_adi + ".IS"].get("guncel", 0.0)
                    if v_adi in fiyatlar_hepsi: return fiyatlar_hepsi[v_adi].get("guncel", 0.0)
                    return 0.0
                
                df_ig["Guncel Fiyat"] = df_ig["Varlık"].apply(fiyat_getir_gecmis)
                df_ig["Satılmasaydı K/Z (TL)"] = df_ig.apply(lambda r: (r["Guncel Fiyat"] - r["Maliyet"]) * r["Lot"] if r["Guncel Fiyat"] > 0 else 0.0, axis=1)
                df_ig["Satılmasaydı K/Z (%)"] = df_ig.apply(lambda r: ((r["Guncel Fiyat"] - r["Maliyet"]) / r["Maliyet"]) * 100 if r["Guncel Fiyat"] > 0 and r["Maliyet"] > 0 else 0.0, axis=1)

                df_ig = df_ig.sort_values(by="Tarih", ascending=False).reset_index(drop=True)
                df_ig.insert(0, "🗑️ Sil", False)
                
                sutunlar = ["🗑️ Sil", "Alım Tarihi", "Tarih", "Gün", "Varlık", "Lot", "Fiyat", "Satış Tutarı (TL)", "Maliyet", "Satılmasaydı K/Z (TL)", "Satılmasaydı K/Z (%)", "Kâr/Zarar (TL)", "Kâr/Zarar (%)", "id"]
                df_ig = df_ig[[c for c in sutunlar if c in df_ig.columns]]
                
                df_ig["Alım Tarihi"] = pd.to_datetime(df_ig["Alım Tarihi"])
                df_ig["Tarih"] = pd.to_datetime(df_ig["Tarih"])
                
                edited_ig = st.data_editor(
                    df_ig,
                    column_config={
                        "id": None,
                        "🗑️ Sil": st.column_config.CheckboxColumn("🗑️ Sil", default=False),
                        "Alım Tarihi": st.column_config.DateColumn("Alım", format="DD.MM.YYYY", disabled=False),
                        "Tarih": st.column_config.DateColumn("Satım", format="DD.MM.YYYY", disabled=False),
                        "Gün": st.column_config.NumberColumn("Geçirilen Gün", disabled=True),
                        "Varlık": st.column_config.TextColumn("Varlık", disabled=False),
                        "Lot": st.column_config.NumberColumn("Lot", format="%.2f", disabled=False, min_value=0.01),
                        "Fiyat": st.column_config.NumberColumn("Satış Fiyatı", format="%.4f ₺", disabled=False, min_value=0.0),
                        "Satış Tutarı (TL)": st.column_config.NumberColumn("Satış Tutarı (TL)", format="%.2f ₺", disabled=True),
                        "Maliyet": st.column_config.NumberColumn("Maliyet Fiyatı", format="%.4f ₺", disabled=False, min_value=0.0),
                        "Satılmasaydı K/Z (TL)": st.column_config.NumberColumn("Satılmasaydı K/Z (TL)", format="%.2f ₺", disabled=True),
                        "Satılmasaydı K/Z (%)": st.column_config.NumberColumn("Satılmasaydı K/Z (%)", format="%% %.2f", disabled=True),
                        "Kâr/Zarar (TL)": st.column_config.NumberColumn("Kâr/Zarar (TL)", format="%.2f ₺", disabled=True),
                        "Kâr/Zarar (%)": st.column_config.NumberColumn("Kâr/Zarar (%)", format="%% %.2f", disabled=True)
                    },
                    use_container_width=True, hide_index=True, height=int((min(len(df_ig), 25) + 1) * 36 + 40), key=f"editor_ig_{secili_cuzdan}"
                )
                
                if st.button("💾 İşlem Geçmişindeki Değişiklikleri Kaydet (Sil / Düzenle)", type="primary"):
                    yeni_liste = []
                    degisim_var = False
                    for idx, row in edited_ig.iterrows():
                        if not row["🗑️ Sil"]:
                            kz_tl = 0.0
                            kz_yuzde = 0.0
                            maliyet = float(row["Maliyet"])
                            fiyat = float(row["Fiyat"])
                            lot = float(row["Lot"])
                            
                            if maliyet > 0:
                                kz_tl = (fiyat - maliyet) * lot
                                kz_yuzde = ((fiyat - maliyet) / maliyet) * 100
                                
                            tarih_v = row["Tarih"]
                            if pd.isna(tarih_v) or tarih_v is None: 
                                t_str = datetime.today().strftime("%Y-%m-%d")
                            elif isinstance(tarih_v, str): 
                                t_str = tarih_v[:10]
                            else: 
                                t_str = tarih_v.strftime("%Y-%m-%d")
                                
                            alim_v = row.get("Alım Tarihi", t_str)
                            if pd.isna(alim_v) or alim_v is None: 
                                a_str = t_str
                            elif isinstance(alim_v, str): 
                                a_str = alim_v[:10]
                            else: 
                                a_str = alim_v.strftime("%Y-%m-%d")
                                
                            yeni_liste.append({
                                "id": row["id"],
                                "Alım Tarihi": a_str,
                                "Tarih": t_str,
                                "Tip": "Satım",
                                "Varlık": str(row["Varlık"]).upper(),
                                "Lot": lot,
                                "Fiyat": fiyat,
                                "Maliyet": maliyet,
                                "Kâr/Zarar (TL)": kz_tl,
                                "Kâr/Zarar (%)": kz_yuzde
                            })
                            degisim_var = True
                        else:
                            degisim_var = True
                            
                    if degisim_var:
                        islem_gecmisi[secili_cuzdan] = yeni_liste
                        islem_gecmisi_kaydet(islem_gecmisi)
                        st.rerun()
            else:
                st.info("Bu cüzdana ait henüz kaydedilmiş veya filtreye uyan bir işlem geçmişi bulunmuyor.")

        if gecmis_verisi:
            st.markdown("---")
            col_g1, col_g2, col_g3 = st.columns(3)
            with col_g1:
                st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>Grafik Eğrisi:</p>", unsafe_allow_html=True)
                grafik_turu2 = st.radio("Grafik Eğrisi:", ["Güncel Değer (TL)", "Kâr/Zarar (%)"], horizontal=True, key="gr_tur2", label_visibility="collapsed")
            with col_g2:
                st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>📊 Endeks Kıyasla:</p>", unsafe_allow_html=True)
                kiyaslamalar2 = st.multiselect("Endeks Kıyasla", ["BİST100", "BİST30", "BİST50", "BİST Tüm", "Ons Altın"], key=f"kiyas_mod2_{secili_cuzdan}", label_visibility="collapsed")
            with col_g3:
                st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 5px; color: #31333F;'>➕ Hisse Kıyasla (Arama):</p>", unsafe_allow_html=True)
                ozel_kiyas_hisse2 = st.multiselect("Hisse Kıyasla", TUM_HISSE_SECENEKLERI, key=f"ozel_kiyas_mod2_{secili_cuzdan}", placeholder="Hisse ara (Örn: THYAO)", label_visibility="collapsed")
            
            hedef_anahtar = secili_cuzdan
            grafik_verisi = [{
                "Tarih": t, 
                "Kâr/Zarar (%)": round(((d[hedef_anahtar]["deger"] - d[hedef_anahtar]["yatirim"]) / d[hedef_anahtar]["yatirim"] * 100), 2) if d[hedef_anahtar].get("yatirim", 0) > 0 else 0.0, 
                "Güncel Değer (TL)": d[hedef_anahtar].get("deger", 0.0),
                "Yatırım Tutarı": f"{d[hedef_anahtar].get('yatirim', 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"
            } for t, d in gecmis_verisi.items() if hedef_anahtar in d]
                    
            if grafik_verisi:
                df_gecmis = pd.DataFrame(grafik_verisi); df_gecmis["Tarih"] = pd.to_datetime(df_gecmis["Tarih"]); df_gecmis = df_gecmis.sort_values(by="Tarih")
                zaman_filtresi = st.selectbox("⏳ Görüntülenecek Periyot:", ["Son 1 Hafta", "Son 1 Ay", "Son 3 Ay", "Son 6 Ay", "Son 1 Yıl", "Tüm Zamanlar", "Özel Tarih"], index=5)
                
                limit_tarihi = None
                if zaman_filtresi != "Tüm Zamanlar":
                    if zaman_filtresi == "Son 1 Hafta": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=7))
                    elif zaman_filtresi == "Son 1 Ay": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=30))
                    elif zaman_filtresi == "Son 3 Ay": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=90))
                    elif zaman_filtresi == "Son 6 Ay": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=180))
                    elif zaman_filtresi == "Son 1 Yıl": limit_tarihi = pd.to_datetime(datetime.now().date() - timedelta(days=365))
                    elif zaman_filtresi == "Özel Tarih":
                        col_t1, col_t2 = st.columns(2)
                        with col_t1: bas_tarih = st.date_input("Başlangıç Tarihi", df_gecmis["Tarih"].min().date(), format="DD/MM/YYYY")
                        with col_t2: bitis_tarih = st.date_input("Bitiş Tarihi", df_gecmis["Tarih"].max().date(), format="DD/MM/YYYY")
                        limit_tarihi = None
                        df_gecmis = df_gecmis[(df_gecmis["Tarih"].dt.date >= bas_tarih) & (df_gecmis["Tarih"].dt.date <= bitis_tarih)]
                    if limit_tarihi: df_gecmis = df_gecmis[df_gecmis["Tarih"] >= limit_tarihi]
                
                if len(df_gecmis) > 0:
                    y_secim = "Kâr/Zarar (%)" if grafik_turu2 == "Kâr/Zarar (%)" else "Güncel Değer (TL)"
                    cizilecek_y = [y_secim]
                    
                    secili_kiyaslar2 = list(kiyaslamalar2) + list(ozel_kiyas_hisse2)
                    
                    if secili_kiyaslar2:
                        df_kiyas = kiyas_verilerini_getir(tuple(ozel_kiyas_hisse2))
                        if not df_kiyas.empty:
                            df_gecmis["Tarih_Date"] = df_gecmis["Tarih"].dt.date
                            df_gecmis = pd.merge(df_gecmis, df_kiyas, left_on="Tarih_Date", right_on="Tarih", how="left").drop(columns=["Tarih_y", "Tarih_Date"]).rename(columns={"Tarih_x": "Tarih"})
                            
                            ilk_portfoy_val = df_gecmis[y_secim].iloc[0]
                            
                            for k_secim in secili_kiyaslar2:
                                if k_secim in df_gecmis.columns and not df_gecmis[k_secim].isna().all():
                                    df_gecmis[k_secim] = df_gecmis[k_secim].ffill().bfill()
                                    
                                    if len(df_gecmis) > 1 and df_gecmis[k_secim].nunique() <= 1:
                                        st.warning(f"⚠️ '{k_secim}' için Yahoo Finance üzerinde yeterli geçmiş veri bulunamadı. Grafiğe eklenemedi.")
                                        continue
                                        
                                    ilk_k = df_gecmis[k_secim].iloc[0]
                                    col_name = f"{k_secim} (Kıyas)"
                                    if y_secim == "Kâr/Zarar (%)":
                                        df_gecmis[col_name] = ((df_gecmis[k_secim] - ilk_k) / ilk_k) * 100 + ilk_portfoy_val
                                    else:
                                        df_gecmis[col_name] = (df_gecmis[k_secim] / ilk_k) * ilk_portfoy_val
                                    cizilecek_y.append(col_name)

                    fig_line = px.line(df_gecmis, x="Tarih", y=cizilecek_y, markers=True, labels={"value": y_secim, "variable": "Gösterge"})
                    fig_line.update_layout(xaxis_title="Tarih", yaxis_title=y_secim, hovermode="x unified")
                    st.plotly_chart(fig_line, use_container_width=True)

            st.markdown("---")
            with st.expander("📝 Geçmiş Kayıtları Yönet (Düzenle & Sil)", expanded=True):
                editor_data = []
                sorted_dates = sorted(gecmis_verisi.keys())
                prev_deg = None
                prev_h_deg = None
                
                for t in sorted_dates:
                    d = gecmis_verisi[t]
                    if hedef_anahtar in d:
                        yat = d[hedef_anahtar].get("yatirim", 0.0)
                        deg = d[hedef_anahtar].get("deger", 0.0)
                        
                        h_deg = d[hedef_anahtar].get("hisse_deger", 0.0) + d[hedef_anahtar].get("takas_deger", 0.0)
                        
                        kz_tl = deg - yat
                        kz_y = ((deg - yat) / yat * 100) if yat > 0 else 0
                        
                        if prev_deg is not None and prev_deg > 0:
                            g_fark_tl = deg - prev_deg
                            g_fark_y = (g_fark_tl / prev_deg) * 100
                        else:
                            g_fark_tl = 0.0
                            g_fark_y = 0.0
                            
                        if prev_h_deg is not None and prev_h_deg > 0:
                            g_h_fark_tl = h_deg - prev_h_deg
                            g_h_fark_y = (g_h_fark_tl / prev_h_deg) * 100
                        else:
                            g_h_fark_tl = 0.0
                            g_h_fark_y = 0.0
                            
                        editor_data.append({
                            "🗑️ Sil": False, "Tarih": t, "Yatırım (TL)": yat, "Güncel Değer (TL)": deg,
                            "Günlük Fark (TL)": g_fark_tl, "Günlük Fark (%)": g_fark_y,
                            "Hisse Günlük Fark (TL)": g_h_fark_tl, "Hisse Günlük Fark (%)": g_h_fark_y,
                            "Kâr/Zarar (TL)": kz_tl, "Kâr/Zarar (%)": kz_y
                        })
                        
                        prev_deg = deg
                        prev_h_deg = h_deg

                if editor_data:
                    df_editor = pd.DataFrame(editor_data).sort_values(by="Tarih", ascending=False).reset_index(drop=True)
                    df_editor["Tarih"] = pd.to_datetime(df_editor["Tarih"])
                    
                    edited_history = st.data_editor(
                        df_editor,
                        column_config={
                            "🗑️ Sil": st.column_config.CheckboxColumn("🗑️ Sil", default=False),
                            "Tarih": st.column_config.DateColumn("Tarih", format="DD.MM.YYYY", disabled=True),
                            "Yatırım (TL)": st.column_config.NumberColumn("Yatırım (TL)", min_value=0.0, format="%.2f ₺"),
                            "Güncel Değer (TL)": st.column_config.NumberColumn("Güncel Değer (TL)", min_value=0.0, format="%.2f ₺"),
                            "Günlük Fark (TL)": st.column_config.NumberColumn("Günlük Fark (TL)", format="%.2f ₺", disabled=True),
                            "Günlük Fark (%)": st.column_config.NumberColumn("Günlük Fark (%)", format="%% %.2f", disabled=True),
                            "Hisse Günlük Fark (TL)": st.column_config.NumberColumn("Hisse Günlük Fark (TL)", format="%.2f ₺", disabled=True),
                            "Hisse Günlük Fark (%)": st.column_config.NumberColumn("Hisse Günlük Fark (%)", format="%% %.2f", disabled=True),
                            "Kâr/Zarar (TL)": st.column_config.NumberColumn("Kâr/Zarar (TL)", format="%.2f ₺", disabled=True),
                            "Kâr/Zarar (%)": st.column_config.NumberColumn("Kâr/Zarar (%)", format="%% %.2f", disabled=True)
                        },
                        use_container_width=True, hide_index=True, key=f"hist_editor_tekil"
                    )

                    if st.button("💾 Geçmişi Güncelle", type="primary", key="btn_hist_tekil"):
                        degisiklik_var = False
                        for idx, row in edited_history.iterrows():
                            tarih_val = row["Tarih"]
                            if isinstance(tarih_val, str): tarih = tarih_val[:10]
                            else: tarih = tarih_val.strftime("%Y-%m-%d")
                                
                            if row["🗑️ Sil"]:
                                if secili_cuzdan in gecmis_verisi.get(tarih, {}):
                                    del gecmis_verisi[tarih][secili_cuzdan]; degisiklik_var = True
                                    if not gecmis_verisi[tarih]: del gecmis_verisi[tarih]
                            else:
                                if tarih in gecmis_verisi and secili_cuzdan in gecmis_verisi[tarih]:
                                    yeni_yat = float(row["Yatırım (TL)"])
                                    yeni_deg = float(row["Güncel Değer (TL)"])
                                    eski_yat = gecmis_verisi[tarih][secili_cuzdan]["yatirim"]
                                    eski_deg = gecmis_verisi[tarih][secili_cuzdan]["deger"]

                                    if yeni_yat != eski_yat or yeni_deg != eski_deg:
                                        gecmis_verisi[tarih][secili_cuzdan]["yatirim"] = yeni_yat
                                        gecmis_verisi[tarih][secili_cuzdan]["deger"] = yeni_deg
                                        degisiklik_var = True

                        if degisiklik_var:
                            gecmis_kaydet(gecmis_verisi)
                            st.success("✅ Geçmiş kayıtlar güncellendi! Sayfa yenileniyor...")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.info("Değişiklik bulunamadı.")
                else:
                    st.info("Henüz geçmiş kayıt bulunmuyor.")

    else:
        st.info("Sistemde henüz kayıtlı hiçbir varlık bulunmuyor.")