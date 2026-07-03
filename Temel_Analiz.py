import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import plotly.express as px
from isyatirimhisse import fetch_financials
from datetime import datetime
import os
import json
from google import genai

st.set_page_config(page_title="Temel Analiz", layout="wide")

st.title("📊 Şirket Bilanço ve Temel Analiz")
st.markdown("---")

# ==========================================
# YARDIMCI FONKSİYONLAR VE HAFIZA YÖNETİMİ
# ==========================================
API_AYAR_DOSYASI = "api_ayarlar.json"

def api_anahtari_getir():
    try:
        if "gemini_api_key" in st.secrets:
            return st.secrets["gemini_api_key"]
    except Exception:
        pass
    if os.path.exists(API_AYAR_DOSYASI):
        try:
            with open(API_AYAR_DOSYASI, "r", encoding="utf-8") as f:
                veri = json.load(f)
                return veri.get("gemini_api_key", "")
        except: return ""
    return ""

def api_anahtari_kaydet(anahtar):
    with open(API_AYAR_DOSYASI, "w", encoding="utf-8") as f:
        json.dump({"gemini_api_key": anahtar}, f)

def hisse_listesi_yukle():
    yedek_liste = ["TUPRS", "THYAO", "ISCTR", "KCHOL", "SAHOL", "EREGL", "ASELS", "BIMAS", "AKBNK", "YKBNK", "GARAN", "SISE", "TCELL", "FROTO", "TOASO", "PGSUS", "ENKAI", "SASA", "HEKTS", "KRDMD"]
    
    dosya_yollari = ["endeksler.json", "../endeksler.json"]
    for yol in dosya_yollari:
        if os.path.exists(yol):
            try:
                with open(yol, "r", encoding="utf-8") as f:
                    veri = json.load(f)
                    tum_hisseler = set()
                    for liste in veri.values():
                        for h in liste:
                            tum_hisseler.add(h.replace(".IS", ""))
                    if tum_hisseler:
                        return sorted(list(tum_hisseler))
            except:
                pass
                
    return sorted(yedek_liste)

hisse_havuzu = hisse_listesi_yukle()

# --- Nadaraya-Watson Algoritması (Teknik Analiz İçin) ---
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

# --- Arama Çubuğu ---
col1, col2 = st.columns([1, 4])
with col1:
    hisse_kodu = st.selectbox(
        "🔍 Hisse Seçin veya Yazın:", 
        options=hisse_havuzu, 
        index=None, 
        placeholder="Örn: TUPRS yazın..." 
    )

def metrik_bul(df, aranacak_kelimeler, son_d, onceki_d):
    for kelime in aranacak_kelimeler:
        mask = df.index.astype(str).str.contains(kelime, case=False, na=False)
        if mask.any():
            guncel = df.loc[mask, son_d].values[0]
            eski = df.loc[mask, onceki_d].values[0]
            if pd.isna(guncel): guncel = 0
            if pd.isna(eski): eski = 0
            degisim = ((guncel - eski) / abs(eski)) * 100 if eski != 0 else 0
            return guncel, degisim
    return 0, 0

def format_para(val):
    if pd.isna(val) or val == "": return "-"
    try:
        v = float(val)
        if abs(v) >= 1e9:
            return f"{v/1e9:.2f} Mr"
        elif abs(v) >= 1e6:
            return f"{v/1e6:.2f} M"
        elif abs(v) >= 1e3:
            return f"{v/1e3:.1f} B"
        else:
            return f"{v:.1f}"
    except:
        return val

def format_degisim(val):
    if pd.isna(val): return "-"
    if val > 0: return f"🟢 +{val:.1f}%"
    elif val < 0: return f"🔴 {val:.1f}%"
    else: return "➖ 0.0%"

# --- BUTON HAFIZASI VE İŞLEM YÖNETİMİ ---
if st.button("Analiz Et", type="primary"):
    if hisse_kodu:
        st.session_state["aktif_hisse"] = hisse_kodu
    else:
        st.warning("⚠️ Lütfen analiz etmek için bir hisse senedi seçin veya yazın.")

if st.session_state.get("aktif_hisse") == hisse_kodu and hisse_kodu is not None:
    islem_kodu = hisse_kodu.replace(".IS", "") 
    
    try:
        with st.spinner(f"{islem_kodu} için veriler çekiliyor ve hesaplanıyor..."):
            
            # --- VERİ ÇEKME ---
            son_yil = datetime.now().year
            baslangic_yili = str(son_yil - 4) 
            
            mali_tablo_orijinal = fetch_financials(symbols=islem_kodu, start_year=baslangic_yili, exchange="TRY")
            mali_tablo = mali_tablo_orijinal.copy() if mali_tablo_orijinal is not None else None

            yf_kodu = f"{islem_kodu}.IS"
            tk = yf.Ticker(yf_kodu)
            temettu_verisi = tk.dividends
            info = tk.info 

            # --- DÖVİZ KURLARI VE GÜNCEL FİYAT (THYAO VB. İÇİN) ---
            fin_para_birimi = info.get('financialCurrency', 'TRY')
            usd_kur = 32.0  
            eur_kur = 35.0  
            usd_hist = pd.Series(dtype=float)
            eur_hist = pd.Series(dtype=float)
            
            if fin_para_birimi in ['USD', 'EUR']:
                try:
                    if fin_para_birimi == 'USD':
                        usd_df = yf.download("TRY=X", period="5y", progress=False)
                        if not usd_df.empty: 
                            usd_hist = usd_df['Close'].squeeze()
                            usd_kur = float(usd_hist.iloc[-1])
                    elif fin_para_birimi == 'EUR':
                        eur_df = yf.download("EURTRY=X", period="5y", progress=False)
                        if not eur_df.empty: 
                            eur_hist = eur_df['Close'].squeeze()
                            eur_kur = float(eur_hist.iloc[-1])
                except: pass

            fyt_anlik = info.get('currentPrice', info.get('previousClose', 0))
            
            # 1. Varsayılan Güncel PD/DD Çekimi (Yedek olarak tutulur)
            pddd_guncel = info.get('priceToBook')
            bv = info.get('bookValue')
            if bv and bv > 0 and fyt_anlik > 0:
                if fin_para_birimi == 'USD': gercek_bv_tl = bv * usd_kur
                elif fin_para_birimi == 'EUR': gercek_bv_tl = bv * eur_kur
                else: gercek_bv_tl = bv
                pddd_guncel = fyt_anlik / gercek_bv_tl

            # --- YENİ 5 YILLIK PD/DD ORTALAMASI VE GÜNCEL PD/DD SAĞLAMASI ---
            pddd_5y_ort = None
            try:
                bs = tk.balance_sheet
                current_shares = info.get('sharesOutstanding', None)
                
                if not bs.empty and current_shares is not None and current_shares > 0:
                    bs_idx_lower = [str(i).lower() for i in bs.index]
                    eq_idx = next((i for i, name in enumerate(bs_idx_lower) if "stockholders equity" in name or "total equity" in name), None)
                    
                    if eq_idx is not None:
                        eq_row = bs.iloc[eq_idx]
                        
                        # --- ÖNEMLİ: Güncel PD/DD'yi Bilançodan Kesin Olarak Hesapla (5 Yıllık Mantıkla Aynı) ---
                        try:
                            guncel_ozkaynak = float(eq_row.iloc[0])
                            if guncel_ozkaynak > 0 and fyt_anlik > 0:
                                kur_carpani = 1.0
                                if fin_para_birimi == 'USD': kur_carpani = usd_kur
                                elif fin_para_birimi == 'EUR': kur_carpani = eur_kur
                                
                                gercek_ozkaynak_tl = guncel_ozkaynak * kur_carpani
                                piyasa_degeri = fyt_anlik * current_shares
                                pddd_guncel = piyasa_degeri / gercek_ozkaynak_tl
                        except:
                            pass
                            
                        # --- Geçmiş 5 Yılın Ortalaması ---
                        hist_prices_5y = tk.history(period="5y", interval="1mo")
                        pddd_degerleri = []
                        for col_date in bs.columns:
                            try:
                                ozkaynak = float(eq_row[col_date])
                                if pd.isna(ozkaynak) or ozkaynak <= 0: continue
                                
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
                                
                                if hist_prices_5y.index.tz is not None:
                                    target_dt_fiyat = pd.to_datetime(col_date).tz_localize(hist_prices_5y.index.tz)
                                else:
                                    target_dt_fiyat = pd.to_datetime(col_date).tz_localize(None)
                                    
                                en_yakin_idx = hist_prices_5y.index.get_indexer([target_dt_fiyat], method='nearest')[0]
                                fiyat = float(hist_prices_5y.iloc[en_yakin_idx]['Close'])
                                
                                tarihsel_piyasa_degeri = fiyat * current_shares
                                
                                if tarihsel_piyasa_degeri > 0 and gercek_ozkaynak_tl > 0:
                                    pddd_degerleri.append(tarihsel_piyasa_degeri / gercek_ozkaynak_tl)
                            except:
                                continue
                                
                        if pddd_degerleri:
                            pddd_5y_ort = float(np.mean(pddd_degerleri))
            except Exception:
                pass

            st.success("Veriler başarıyla çekildi!")
            
            # --- 4 SEKME ---
            tab1, tab2, tab3, tab4 = st.tabs(["📈 Özet Bilanço", "💰 Temettü Geçmişi", "ℹ️ Profil ve Çarpanlar", "🤖 Yapay Zeka Yorumu"])
            
            # ==========================================
            # SEKME 1: ÖZET BİLANÇO
            # ==========================================
            with tab1:
                st.subheader(f"{islem_kodu} Özet Finansal Görünüm")
                if mali_tablo is not None and not mali_tablo.empty:
                    ozet_kalemler = [
                        "Dönen Varlıklar", "Duran Varlıklar", "TOPLAM VARLIKLAR", 
                        "Kısa Vadeli Yükümlülükler", "Uzun Vadeli Yükümlülükler", 
                        "Ana Ortaklığa Ait Özkaynaklar", "Özkaynaklar",
                        "Satış Gelirleri", "BRÜT KAR (ZARAR)", "FAALİYET KARI (ZARARI)", "DÖNEM KARI (ZARARI)"
                    ]
                    if 'FINANCIAL_ITEM_NAME_TR' in mali_tablo.columns:
                        mali_tablo = mali_tablo[mali_tablo['FINANCIAL_ITEM_NAME_TR'].isin(ozet_kalemler)]
                        mali_tablo.set_index('FINANCIAL_ITEM_NAME_TR', inplace=True)
                        mali_tablo.index.name = "Bilanço Kalemi"
                        mali_tablo = mali_tablo.drop(columns=['FINANCIAL_ITEM_CODE', 'FINANCIAL_ITEM_NAME_EN', 'SYMBOL'], errors='ignore')

                    for col in mali_tablo.columns:
                        mali_tablo[col] = pd.to_numeric(mali_tablo[col], errors='coerce')

                    mali_tablo = mali_tablo[mali_tablo.columns[::-1]]
                    sayisal_sutunlar = mali_tablo.columns.tolist()
                    
                    if len(sayisal_sutunlar) >= 2:
                        son_donem = sayisal_sutunlar[0]
                        onceki_donem = sayisal_sutunlar[1]
                        
                        net_kar, net_kar_degisim = metrik_bul(mali_tablo, ["DÖNEM KARI", "Dönem Karı"], son_donem, onceki_donem)
                        esas_faaliyet, esas_faaliyet_degisim = metrik_bul(mali_tablo, ["FAALİYET KARI", "Faaliyet Karı"], son_donem, onceki_donem)
                        ozkaynak, ozkaynak_degisim = metrik_bul(mali_tablo, ["Ana Ortaklığa Ait Özkaynaklar", "Özkaynaklar"], son_donem, onceki_donem)
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric(label="💰 Net Dönem Kârı", value=format_para(net_kar), delta=f"% {net_kar_degisim:.1f}")
                        m2.metric(label="⚙️ Faaliyet Kârı", value=format_para(esas_faaliyet), delta=f"% {esas_faaliyet_degisim:.1f}")
                        m3.metric(label="🛡️ Toplam Özkaynaklar", value=format_para(ozkaynak), delta=f"% {ozkaynak_degisim:.1f}")
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        degisim_serisi = ((mali_tablo[son_donem] - mali_tablo[onceki_donem]) / mali_tablo[onceki_donem].abs()) * 100
                        mali_tablo.insert(0, 'Gidişat (%)', degisim_serisi.apply(format_degisim))
                        
                    for col in sayisal_sutunlar:
                        mali_tablo[col] = mali_tablo[col].apply(format_para)

                    st.dataframe(mali_tablo, use_container_width=True, height=450)
                else:
                    st.warning("Bu hisse için mali tablo verisi bulunamadı.")

            # ==========================================
            # SEKME 2: TEMETTÜ
            # ==========================================
            with tab2:
                st.subheader(f"{islem_kodu} Temettü Dağıtım Geçmişi")
                if not temettu_verisi.empty:
                    df_temettu = pd.DataFrame(temettu_verisi).reset_index()
                    df_temettu.columns = ['Tarih', 'Temettü Miktarı (TL/Hisse)']
                    df_temettu['Tarih'] = df_temettu['Tarih'].dt.date
                    df_temettu = df_temettu.sort_values('Tarih', ascending=False)
                    
                    col_t1, col_t2 = st.columns([1, 2])
                    with col_t1:
                        st.dataframe(df_temettu, hide_index=True, use_container_width=True)
                    with col_t2:
                        fig_temettu = px.bar(
                            df_temettu, x='Tarih', y='Temettü Miktarı (TL/Hisse)', 
                            title=f"{islem_kodu} Yıllara Göre Hisse Başı Net Temettü",
                            color_discrete_sequence=['#00cc96']
                        )
                        st.plotly_chart(fig_temettu, use_container_width=True)
                else:
                    st.warning("Bu şirket için kayıtlı temettü verisi bulunamadı veya şirket temettü dağıtmıyor.")

            # ==========================================
            # SEKME 3: PROFİL VE ÇARPANLAR
            # ==========================================
            with tab3:
                st.subheader(f"ℹ️ {islem_kodu} Şirket Profili ve Anlık Çarpanlar")
                
                if info:
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown("### 🏢 Şirket Kimliği")
                        st.markdown(f"**Sektör:** {info.get('sector', 'Belirtilmedi')}")
                        st.markdown(f"**Faaliyet Alanı:** {info.get('industry', 'Belirtilmedi')}")
                        st.markdown(f"**Çalışan Sayısı:** {info.get('fullTimeEmployees', 'Bilinmiyor')}")
                        st.markdown(f"**Web Sitesi:** {info.get('website', '-')}")
                        st.markdown("---")
                        st.markdown("**Şirket Özeti:**")
                        st.caption(info.get('longBusinessSummary', 'Şirket profili açıklaması bulunamadı.'))
                    
                    with c2:
                        st.markdown("### 📊 Anlık Çarpanlar")
                        fk = info.get('trailingPE')
                        st.metric("F/K Oranı (Fiyat/Kazanç)", f"{fk:.2f}" if fk else "Yok")
                        
                        # --- Özel Hesaplanan Güncel PD/DD'nin Gösterimi ---
                        pddd_delta_metni = None
                        if pddd_guncel and pddd_5y_ort:
                            pddd_sapma = ((pddd_guncel - pddd_5y_ort) / pddd_5y_ort) * 100
                            pddd_delta_metni = f"5Y Ort: {pddd_5y_ort:.2f} (%{pddd_sapma:+.1f})"
                        
                        st.metric(
                            label="PD/DD (Piyasa/Defter Değeri)", 
                            value=f"{pddd_guncel:.2f}" if pddd_guncel else "Yok", 
                            delta=pddd_delta_metni, 
                            delta_color="inverse" if pddd_delta_metni else "normal"
                        )
                        
                        roe = info.get('returnOnEquity')
                        st.metric("Özkaynak Kârlılığı (ROE)", f"% {roe*100:.2f}" if roe else "Yok")
                        marj = info.get('profitMargins')
                        st.metric("Net Kâr Marjı", f"% {marj*100:.2f}" if marj else "Yok")
                else:
                    st.warning("Yahoo Finance üzerinden şirket detayları çekilemedi.")

            # ==========================================
            # SEKME 4: YAPAY ZEKA YORUMU (TEKNİK + TEMEL + ENDEKS)
            # ==========================================
            with tab4:
                st.subheader(f"🤖 {islem_kodu} İçin Kapsamlı Gemini Yapay Zeka Analizi")
                st.markdown("Yapay zeka; şirketin çarpanlarını, teknik analizini ve **BIST100 endeksinin genel durumunu** harmanlayarak yapılandırılmış bir rapor sunar.")
                
                kayitli_key = api_anahtari_getir()
                api_key = st.text_input("Gemini API Anahtarınızı Girin (Sadece ilk seferde gerekir):", value=kayitli_key, type="password", key="gemini_api_key_input")
                
                if api_key and api_key != kayitli_key:
                    api_anahtari_kaydet(api_key)
                
                if st.button("🧠 Şirketi Kapsamlı Analiz Et", type="primary", use_container_width=True):
                    if not api_key:
                        st.warning("Lütfen analizi başlatmak için bir Gemini API anahtarı girin.")
                    else:
                        with st.spinner("Gemini verileri inceliyor, endeksi kontrol ediyor ve yorumluyor..."):
                            try:
                                client = genai.Client(api_key=api_key)
                                
                                # --- Temel Verilerin Toplanması ---
                                fk_val = info.get('trailingPE', 'Bilinmiyor')
                                pddd_val = f"{pddd_guncel:.2f}" if pddd_guncel is not None else "Bilinmiyor"
                                pddd_5y_val = f"{pddd_5y_ort:.2f}" if pddd_5y_ort else "Hesaplanamadı (Veri Eksik)"
                                roe_val = info.get('returnOnEquity', 'Bilinmiyor')
                                marj_val = info.get('profitMargins', 'Bilinmiyor')
                                sektor_val = info.get('sector', 'Bilinmiyor')
                                
                                # --- Endeks (BIST100) Verisinin Çekilmesi ---
                                endeks_bilgi = "Endeks verisi hesaplanamadı."
                                try:
                                    df_endeks = yf.download("XU100.IS", period="6mo", interval="1d", progress=False)
                                    if not df_endeks.empty and len(df_endeks) > 50:
                                        endeks_close = df_endeks['Close'].squeeze().dropna()
                                        endeks_fyt = float(endeks_close.iloc[-1])
                                        endeks_e50 = endeks_close.ewm(span=50, min_periods=1).mean().iloc[-1]
                                        endeks_trend = "Pozitif (50 Günlük EMA'nın Üzerinde 🟢)" if endeks_fyt > endeks_e50 else "Negatif (50 Günlük EMA'nın Altında 🔴)"
                                        endeks_bilgi = f"BIST100 Anlık Değer: {endeks_fyt:.2f} | Genel Trend: {endeks_trend}"
                                except Exception as e:
                                    endeks_bilgi = f"Endeks verisi çekilemedi. Hata: {e}"

                                # --- Anlık Teknik Sinyalin Hesaplanması ---
                                teknik_bilgi = "Teknik veriler hesaplanamadı."
                                df_tech = yf.download(yf_kodu, period="2y", interval="1d", progress=False)
                                
                                if not df_tech.empty and len(df_tech) > 52:
                                    close = df_tech['Close'].squeeze().dropna()
                                    high = df_tech['High'].squeeze().dropna()
                                    low = df_tech['Low'].squeeze().dropna()
                                    hacim = df_tech['Volume'].squeeze().dropna()
                                    
                                    fyt = float(close.iloc[-1])
                                    e9 = close.ewm(span=9, min_periods=1).mean().iloc[-1]
                                    e21 = close.ewm(span=21, min_periods=1).mean().iloc[-1]
                                    e50 = close.ewm(span=50, min_periods=1).mean().iloc[-1]
                                    e200 = close.ewm(span=200).mean().iloc[-1] if len(close) >= 200 else np.nan
                                    
                                    delta = close.diff()
                                    up = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=1).mean()
                                    down = -delta.where(delta < 0, 0).ewm(alpha=1/14, min_periods=1).mean()
                                    rs = up / down
                                    rsi = (100 - (100 / (1 + rs))).iloc[-1]
                                    
                                    m_c = close.ewm(span=12, min_periods=1).mean() - close.ewm(span=26, min_periods=1).mean()
                                    m_s = m_c.ewm(span=9, min_periods=1).mean()
                                    macd_sart = m_c.iloc[-1] > m_s.iloc[-1]
                                    
                                    s_hacim = float(hacim.iloc[-1])
                                    h_ort20 = float(hacim.rolling(20, min_periods=1).mean().iloc[-1])
                                    h_yuzde = ((s_hacim - h_ort20)/h_ort20)*100 if h_ort20 > 0 else 0
                                    
                                    ma20 = close.rolling(20, min_periods=1).mean().iloc[-1]
                                    std20 = close.rolling(20, min_periods=2).std().iloc[-1]
                                    bbG = (4 * std20) / ma20 if pd.notna(std20) and ma20 > 0 else np.nan
                                    bbg_onay = pd.isna(bbG) or bbG < 0.12
                                    
                                    ts = (high.rolling(9, min_periods=1).max() + low.rolling(9, min_periods=1).min()) / 2
                                    ks = (high.rolling(26, min_periods=1).max() + low.rolling(26, min_periods=1).min()) / 2
                                    ssa = ((ts + ks) / 2).shift(26).iloc[-1]
                                    ssb = ((high.rolling(52, min_periods=1).max() + low.rolling(52, min_periods=1).min()) / 2).shift(26).iloc[-1]
                                    ichi_sart = (fyt > ssa) and (fyt > ssb) if pd.notna(ssa) and pd.notna(ssb) else True
                                    
                                    nwe_series = nadaraya_watson(close)
                                    nwe_sart = fyt > nwe_series.iloc[-1]
                                    
                                    is_kisa_vade_momentum = (fyt > e9) and (h_yuzde > 15) and (rsi > 60)
                                    
                                    if (e9 > e21) and (fyt > e50) and (55 < rsi < 70) and bbg_onay and macd_sart and (s_hacim > hacim.rolling(10).mean().iloc[-1]) and (fyt > e200 if pd.notna(e200) else True) and ichi_sart and nwe_sart:
                                        sinyal = "⚡ GÜÇLÜ AL (Kısa Vade)" if is_kisa_vade_momentum else "🛡️ GÜÇLÜ AL (Orta Vade)"
                                    elif (fyt < e50) and (e9 > e21) and (40 < rsi < 55) and macd_sart and (fyt > e200 if pd.notna(e200) else True) and ichi_sart and nwe_sart:
                                        sinyal = "🌱 KADEMELİ (Dipten Dönüş)"
                                    elif rsi > 75:
                                        sinyal = "⚠️ KÂR AL (Aşırı Alım Bölgesi)"
                                    elif (e9 < e21) and (fyt < e50) and (rsi < 45):
                                        sinyal = "⛔ SAT (Düşüş Trendi)"
                                    else:
                                        sinyal = "⏳ BEKLE (Yatay/Kararsız)"
                                        
                                    teknik_bilgi = f"""
                                    - Anlık Fiyat: {fyt:.2f} TL
                                    - Sistem Radar Sinyali: {sinyal}
                                    - RSI (14): {rsi:.2f}
                                    - MACD Durumu: {"Olumlu (Alış Baskın)" if macd_sart else "Olumsuz (Satış Baskın)"}
                                    - Trend Onayı: Fiyat EMA50'nin {"Üzerinde (Yükseliş Trendi)" if fyt > e50 else "Altında (Düşüş Trendi)"}
                                    """
                                
                                prompt = f"""
                                Sen profesyonel ve objektif bir borsa analisti ve portföy yöneticisisin. 
                                Aşağıda {islem_kodu} hissesine ait Bilanço/Temel veriler, Anlık Teknik veriler ve BIST100 Endeksi genel durumu bulunmaktadır.
                                
                                [TEMEL VERİLER]
                                - Sektör: {sektor_val}
                                - F/K Oranı: {fk_val}
                                - Güncel PD/DD Oranı: {pddd_val}
                                - 5 Yıllık Tarihsel PD/DD Ortalaması: {pddd_5y_val}
                                - Özkaynak Kârlılığı (ROE): {roe_val}
                                - Net Kâr Marjı: {marj_val}
                                
                                [TEKNİK VERİLER]
                                {teknik_bilgi}

                                [ENDEKS VERİSİ (BIST100)]
                                {endeks_bilgi}
                                
                                LÜTFEN AŞAĞIDAKİ FORMATA KESİNLİKLE UYARAK YANIT VER:

                                ## 🎯 Puan: [Buraya 100 üzerinden net bir sayısal puan yaz, örneğin 75/100. Puanı verirken hissenin teknik durumunu ve güncel PD/DD'sinin kendi 5 yıllık ortalamasına kıyasla ucuzluğunu/pahalılığını baz al]

                                ### 📝 Kısa Özet
                                [Hissenin mevcut durumunu sadece 2 veya 3 cümle ile çok net, lafı uzatmadan özetle.]

                                ### 📉 Endeks Değerlendirmesi
                                [BIST100 endeksinin yukarıda verilen mevcut durumunu göz önüne alarak, endeksteki olası bir düşüş veya yükselişin bu hissenin teknik trendini nasıl etkileyebileceğini kısaca yorumla. Hissenin endekse karşı dirençli olup olmadığını belirt.]

                                ### 🔍 Detaylı Analiz
                                - **Temel Durum:** Şirketin sektörüne ve KENDİ 5 YILLIK HISTORİK PD/DD ORTALAMASINA göre ucuz/pahalı veya kârlı/verimsiz olup olmadığını veriler ışığında yorumla. Ucuzluk tuzağı (value trap) olup olmadığını analiz et.
                                - **Teknik Görünüm:** Hissenin mevcut trendini, RSI ve MACD durumunu yorumla.
                                - **Nihai Karar:** Radar sinyalinin (Al/Sat/Bekle) temel tablo ile uyumlu olup olmadığını değerlendirerek stratejini açıkla.
                                
                                **Fırsatlar:**
                                - [Madde 1]
                                - [Madde 2]

                                **Riskler:**
                                - [Madde 1]
                                - [Madde 2]

                                *Bu bir yapay zeka analizidir, yatırım tavsiyesi (YTD) değildir.*
                                """
                                
                                response = client.models.generate_content(
                                    model='gemini-2.5-flash',
                                    contents=prompt,
                                )
                                
                                st.markdown("---")
                                st.write(response.text)
                                
                            except Exception as e:
                                st.error(f"Yapay zeka ile iletişimde bir hata oluştu: Lütfen API anahtarınızı kontrol edin. Detay: {e}")

    except Exception as e:
        st.error(f"⚠️ Veri çekilirken genel bir hata oluştu: {e}")