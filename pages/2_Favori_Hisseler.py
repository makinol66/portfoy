import streamlit as st
import yfinance as yf
import json
import os
import db_sync
import plotly.graph_objects as go
import pandas as pd
import time
from datetime import datetime, date

st.set_page_config(page_title="Favori Hisseler", layout="wide")

# ==========================================
# ÖZEL TASARIM (CSS) VE SOL MENÜ GİZLEME
# ==========================================
st.markdown("""
<style>
    /* Sol taraftaki açılır kapanır menüyü (sidebar) tamamen gizleme */
    [data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    
    /* Kart tasarımları için hafif gölge ve yuvarlatma */
    div[data-testid="stMetricContainer"] {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        padding: 10px;
        border-radius: 10px;
    }
    
    /* Sağ üst köşedeki sil butonunu hizalamak için ufak ayar */
    .sil-btn-hizalama {
        margin-top: -5px;
        margin-right: -10px;
    }
</style>
""", unsafe_allow_html=True)

st.title("⭐ Favori Hisselerim")

# --- KALICI HAFIZA (JSON) AYARLARI ---
DOSYA_ADI = "favoriler.json"
PORTFOY_DOSYASI = "portfoy.json"

varsayilan_liste = {
    "AEFES": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"},
    "ISYAT": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"},
    "KOTON": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"},
    "MIATK": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"},
    "REEDR": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"},
    "THYAO": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"},
    "YATAS": {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"}
}

def favorileri_yukle():
    VARSAYILAN_TARIH = "2026-04-01"
    veri = db_sync.load_data("favoriler", varsayilan_liste.copy())
    
    # Eğer veri eski tip listeyse (Sadece hisse isimleri)
    if isinstance(veri, list): 
        yeni_veri = {hisse: {"takipte": False, "maliyet": 0.0, "tarih": VARSAYILAN_TARIH} for hisse in veri}
        favorileri_kaydet(yeni_veri)
        return yeni_veri
    
    # Eğer sözlükse ama "tarih" anahtarı eksikse (Migration)
    guncel_veri = {}
    for k, v in veri.items():
        guncel_veri[k] = {
            "takipte": v.get("takipte", False),
            "maliyet": v.get("maliyet", 0.0),
            "tarih": v.get("tarih", VARSAYILAN_TARIH)
        }
    return dict(sorted(guncel_veri.items()))

def favorileri_kaydet(liste_sozlugu):
    sirali_liste = dict(sorted(liste_sozlugu.items()))
    db_sync.save_data("favoriler", sirali_liste)

# Sayfa her açıldığında gerçek veriyi dosyadan okut
if "favoriler" not in st.session_state:
    st.session_state.favoriler = favorileri_yukle()
else:
    st.session_state.favoriler = favorileri_yukle()

# --- ANLIK FİYAT HAFIZASI (HIZ İÇİN) ---
if "anlik_veriler" not in st.session_state:
    st.session_state.anlik_veriler = {}

def fiyatlari_internetten_cek(hisse_listesi):
    if not hisse_listesi: return {}
    semboller = [f"{h}.IS" for h in hisse_listesi]
    sonuclar = {}
    try:
        veri = yf.download(semboller, period="5d", interval="1d", progress=False)
        for h in hisse_listesi:
            s = f"{h}.IS"
            try:
                kapanislar = veri['Close'].dropna() if len(hisse_listesi) == 1 else veri['Close'][s].dropna()
                if len(kapanislar) >= 2:
                    fyt = float(kapanislar.iloc[-1])
                    onc = float(kapanislar.iloc[-2])
                    sonuclar[h] = {"fiyat": fyt, "gunluk": ((fyt - onc) / onc) * 100}
                elif len(kapanislar) == 1:
                    sonuclar[h] = {"fiyat": float(kapanislar.iloc[-1]), "gunluk": 0.0}
                else:
                    sonuclar[h] = {"fiyat": 0.0, "gunluk": 0.0}
            except: sonuclar[h] = {"fiyat": 0.0, "gunluk": 0.0}
    except:
        for h in hisse_listesi: sonuclar[h] = {"fiyat": 0.0, "gunluk": 0.0}
    return sonuclar

# --- EXCEL'DEN TÜM HİSSELERİ OKUMA ---
@st.cache_data 
def borsa_hisselerini_getir():
    try:
        df = pd.read_excel("Bist_Tum.xlsx")
        hisseler = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        return sorted(list(set(hisseler))) 
    except Exception:
        return []

tum_hisseler = borsa_hisselerini_getir()

# ==========================================
# 1. BÖLÜM: HİSSE EKLEME VE PORTFÖY ÇEKME PANELİ
# ==========================================
st.markdown("[🚀 Taramaya Dön](../)") 
st.markdown("<br>", unsafe_allow_html=True)

st.markdown("### ➕ Favorilere Yeni Hisse Ekle")
col_e1, col_e2, col_e3, col_bostluk = st.columns([2, 1, 1.5, 2])

with col_e1:
    if tum_hisseler:
        eklenebilir_hisseler = [h for h in tum_hisseler if h not in st.session_state.favoriler]
        yeni_hisse = st.selectbox("Hisse Seçin:", ["Seçiniz..."] + eklenebilir_hisseler, label_visibility="collapsed")
    else:
        yeni_hisse = st.text_input("Hisse Kodu (Örn: ASELS):", label_visibility="collapsed").upper().strip()

with col_e2:
    if st.button("Listeye Ekle", use_container_width=True):
        if yeni_hisse and yeni_hisse != "Seçiniz...":
            if yeni_hisse not in st.session_state.favoriler:
                st.session_state.favoriler[yeni_hisse] = {"takipte": False, "maliyet": 0.0, "tarih": "2026-04-01"}
                st.session_state.favoriler = dict(sorted(st.session_state.favoriler.items()))
                favorileri_kaydet(st.session_state.favoriler)
                st.rerun()
            else:
                st.warning("Bu hisse zaten listenizde mevcut!")

with col_e3:
    if st.button("📥 Portföyden Çek", use_container_width=True, type="secondary"):
        try:
            portfoy_verisi = db_sync.load_data("portfoy", {})
            degisiklik_oldu = False
            for cuzdan_adi, icerik in portfoy_verisi.items():
                for kod, detay in icerik.items():
                    if kod.endswith(".IS"):
                        temiz_hisse = kod.replace(".IS", "")
                        st.session_state.favoriler[temiz_hisse] = {
                            "takipte": True,
                            "maliyet": float(detay.get("maliyet", 0.0)),
                            "tarih": detay.get("alim_tarihi", "2026-04-01")
                        }
                        degisiklik_oldu = True
            
            if degisiklik_oldu:
                st.session_state.favoriler = dict(sorted(st.session_state.favoriler.items()))
                favorileri_kaydet(st.session_state.favoriler)
                st.success("✅ Portföydeki hisseler başarıyla favorilere eklendi!")
                time.sleep(1)
                st.rerun()
            else:
                st.info("Portföyde çekilecek geçerli hisse bulunamadı.")
        except Exception as e:
            st.error("Portföy okunurken bir hata oluştu.")

# ==========================================
# 2. BÖLÜM: CANLI PANO VE TABLO (SEKMELİ)
# ==========================================
st.markdown("---")
col_pano1, col_pano2 = st.columns([4, 1])
with col_pano1:
    st.subheader("📊 Favori Hisseler Panosu")
with col_pano2:
    if st.button("🔄 Fiyatları Güncelle", use_container_width=True, type="primary"):
        with st.spinner("Piyasa verileri güncelleniyor..."):
            st.session_state.anlik_veriler = fiyatlari_internetten_cek(list(st.session_state.favoriler.keys()))

# Eksik verileri tamamla
favori_listesi = list(st.session_state.favoriler.keys())
eksik_hisseler = [h for h in favori_listesi if h not in st.session_state.anlik_veriler]
if eksik_hisseler:
    yeni_cekilenler = fiyatlari_internetten_cek(eksik_hisseler)
    st.session_state.anlik_veriler.update(yeni_cekilenler)

# SEKMELER (TABS)
tab_kartlar, tab_tablo = st.tabs(["🗂️ Kart Görünümü", "📋 Tablo Görünümü (Toplu Yönetim)"])

# --- SEKME 1: KART GÖRÜNÜMÜ ---
with tab_kartlar:
    KOLON_SAYISI = 8 
    hisse_items = list(st.session_state.favoriler.items())

    for i in range(0, len(hisse_items), KOLON_SAYISI):
        satir_kolonlari = st.columns(KOLON_SAYISI)
        
        for j in range(KOLON_SAYISI):
            if i + j < len(hisse_items):
                hisse, veri = hisse_items[i+j]
                with satir_kolonlari[j].container(border=True):
                    gv = st.session_state.anlik_veriler.get(hisse, {"fiyat": 0.0, "gunluk": 0.0})
                    guncel_fiyat = gv["fiyat"]
                    gunluk_getiri = gv["gunluk"]
                    
                    r_gunluk = "green" if gunluk_getiri >= 0 else "red"
                    o_gunluk = "▲" if gunluk_getiri >= 0 else "▼"
                    
                    c_baslik, c_sil_btn = st.columns([3, 1.2])
                    with c_baslik:
                        fintables_url = f"https://fintables.com/sirketler/{hisse}"
                        st.markdown(f"<div style='font-size: 17px; margin-top: 5px;'><b><a href='{fintables_url}' target='_blank' style='text-decoration: none; color: inherit;'>{hisse}</a></b></div>", unsafe_allow_html=True)
                    with c_sil_btn:
                        st.markdown("<div class='sil-btn-hizalama'>", unsafe_allow_html=True)
                        if st.button("✖", key=f"sil_{hisse}", help="Kaldır", use_container_width=True):
                            del st.session_state.favoriler[hisse]
                            favorileri_kaydet(st.session_state.favoriler)
                            st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    st.markdown(f"<div style='text-align: center; font-size: 16px; margin-bottom: 5px;'>{guncel_fiyat:.2f} <span style='color:{r_gunluk};'>{o_gunluk}%{abs(gunluk_getiri):.1f}</span></div>", unsafe_allow_html=True)
                    
                    if veri["takipte"]:
                        try:
                            tarih_obj = datetime.strptime(veri.get("tarih", "2026-04-01"), "%Y-%m-%d")
                            gosterim_tarihi = tarih_obj.strftime("%d.%m.%Y")
                        except:
                            gosterim_tarihi = "01.04.2026"

                        if guncel_fiyat > 0 and veri["maliyet"] > 0:
                            toplam_getiri = ((guncel_fiyat - veri["maliyet"]) / veri["maliyet"]) * 100
                            r_toplam = "green" if toplam_getiri >= 0 else "red"
                            o_toplam = "▲" if toplam_getiri >= 0 else "▼"
                            
                            st.markdown(f"<div style='text-align: center; font-size: 14px; margin-bottom: 2px;'>Mal:{veri['maliyet']:.2f} | <span style='color:{r_toplam};'><b>{o_toplam}%{abs(toplam_getiri):.1f}</b></span></div>", unsafe_allow_html=True)
                        else:
                            st.markdown("<div style='text-align: center; font-size: 14px; margin-bottom: 2px;'>Maliyet: 0.00</div>", unsafe_allow_html=True)
                        
                        st.markdown(f"<div style='text-align: center; font-size: 12px; color: gray; margin-bottom: 5px;'>📅 {gosterim_tarihi}</div>", unsafe_allow_html=True)

                        if st.button("Bırak", key=f"birak_{hisse}", use_container_width=True):
                            st.session_state.favoriler[hisse]["takipte"] = False
                            st.session_state.favoriler[hisse]["maliyet"] = 0.0
                            favorileri_kaydet(st.session_state.favoriler)
                            st.rerun()
                    else:
                        st.write("") 
                        if st.button("Takip", key=f"takip_{hisse}", use_container_width=True, type="primary"):
                            if guncel_fiyat > 0:
                                st.session_state.favoriler[hisse]["takipte"] = True
                                st.session_state.favoriler[hisse]["maliyet"] = float(guncel_fiyat)
                                st.session_state.favoriler[hisse]["tarih"] = datetime.today().strftime("%Y-%m-%d")
                                favorileri_kaydet(st.session_state.favoriler)
                                st.rerun()
                            else:
                                st.error("Hata!")

# --- SEKME 2: TABLO VE TOPLU YÖNETİM ---
with tab_tablo:
    if len(st.session_state.favoriler) == 0:
        st.info("Listenizde hisse bulunmuyor.")
    else:
        st.markdown("Aşağıdaki tablodan hisseleri topluca silebilir, takip durumlarını, maliyetlerini ve tarihlerini elle değiştirebilirsiniz. Değişiklik sonrası **Kaydet** butonuna basın.")
        
        tablo_verisi = []
        for h, v in st.session_state.favoriler.items():
            g_fiyat = st.session_state.anlik_veriler.get(h, {}).get("fiyat", 0.0)
            g_gunluk = st.session_state.anlik_veriler.get(h, {}).get("gunluk", 0.0)
            maliyet = v["maliyet"]
            takip = v["takipte"]
            
            tarih_str = v.get("tarih", "2026-04-01")
            # Metin tarihi gerçek date objesine çeviriyoruz
            try:
                tarih_obj = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            except:
                tarih_obj = date(2026, 4, 1)
            
            kz_yuzde = ((g_fiyat - maliyet) / maliyet * 100) if (takip and maliyet > 0 and g_fiyat > 0) else 0.0
            
            tablo_verisi.append({
                "🗑️ Sil": False,
                "Hisse Adı": h,
                "Takipte": takip,
                "Tarih": tarih_obj,
                "Maliyet Fiyatı": maliyet,
                "Güncel Fiyat": g_fiyat,
                "Günlük (%)": g_gunluk,
                "K/Z (%)": kz_yuzde
            })
            
        df_tablo = pd.DataFrame(tablo_verisi)
        
        hisse_sayisi = len(tablo_verisi)
        gosterilecek_satir = min(hisse_sayisi + 2, 100)
        dinamik_yukseklik = int((gosterilecek_satir * 35) + 40)
        
        edited_df = st.data_editor(
            df_tablo,
            height=dinamik_yukseklik,
            column_config={
                "🗑️ Sil": st.column_config.CheckboxColumn("🗑️ Sil", default=False),
                "Hisse Adı": st.column_config.TextColumn("Hisse Adı", disabled=True),
                "Takipte": st.column_config.CheckboxColumn("Takipte"),
                "Tarih": st.column_config.DateColumn("Tarih", format="DD.MM.YYYY"),
                "Maliyet Fiyatı": st.column_config.NumberColumn("Maliyet Fiyatı", format="%.4f ₺", min_value=0.0),
                "Güncel Fiyat": st.column_config.NumberColumn("Güncel Fiyat", format="%.2f ₺", disabled=True),
                "Günlük (%)": st.column_config.NumberColumn("Günlük (%)", format="%% %.2f", disabled=True),
                "K/Z (%)": st.column_config.NumberColumn("K/Z (%)", format="%% %.2f", disabled=True),
            },
            hide_index=True,
            use_container_width=True,
            key="favori_editor"
        )
        
        if st.button("💾 Tabloyu Kaydet (Değişiklikleri ve Silinenleri Uygula)", type="primary"):
            yeni_favoriler = {}
            degisiklik_var = False
            
            for idx, row in edited_df.iterrows():
                if not row["🗑️ Sil"]:
                    hisse = row["Hisse Adı"]
                    
                    tarih_val = row["Tarih"]
                    if pd.isna(tarih_val) or tarih_val is None:
                        t_str = "2026-04-01"
                    elif isinstance(tarih_val, str):
                        t_str = tarih_val[:10]
                    elif isinstance(tarih_val, (datetime, date)):
                        t_str = tarih_val.strftime("%Y-%m-%d")
                    else:
                        t_str = str(tarih_val)

                    yeni_favoriler[hisse] = {
                        "takipte": row["Takipte"],
                        "maliyet": float(row["Maliyet Fiyatı"]),
                        "tarih": t_str
                    }
                else:
                    degisiklik_var = True 
            
            if yeni_favoriler != st.session_state.favoriler or degisiklik_var:
                st.session_state.favoriler = yeni_favoriler
                favorileri_kaydet(st.session_state.favoriler)
                st.success("✅ Değişiklikler başarıyla kaydedildi!")
                time.sleep(0.5)
                st.rerun()

st.markdown("---")

# ==========================================
# 3. BÖLÜM: ANALİZ VE GRAFİK EKRANI (HIZLANDIRILDI)
# ==========================================

@st.cache_data(ttl=300, show_spinner=False)
def analiz_verilerini_getir(kod, periyot):
    hisse_obj = yf.Ticker(kod)
    try: info = hisse_obj.info
    except: info = {}
    
    try: hizli_veri = hisse_obj.history(period="5d")
    except: hizli_veri = pd.DataFrame()
    
    try: grafik_veri = hisse_obj.history(period=periyot)
    except: grafik_veri = pd.DataFrame()
    
    return info, hizli_veri, grafik_veri

if len(st.session_state.favoriler) == 0:
    st.info("Favori listeniz şu an boş. Lütfen yukarıdaki alandan hisse ekleyin.")
else:
    st.subheader("🔎 Detaylı Grafik ve Analiz")
    hisse_isimleri = list(st.session_state.favoriler.keys())
    secilen_hisse = st.selectbox("Analiz Detaylarını Görmek İstediğiniz Hisseyi Seçin:", hisse_isimleri)
    sorgu_kodu = f"{secilen_hisse}.IS"

    periyot_secimi = st.radio(
        "Grafik Periyodu Seçin:", 
        ["1mo", "1y", "5y", "max"], 
        horizontal=True,
        index=1
    )

    bilgi, gecmis_hizli, gecmis_veri = analiz_verilerini_getir(sorgu_kodu, periyot_secimi)

    st.header(secilen_hisse)
    st.subheader(bilgi.get('longName', 'Şirket Adı Bulunamadı'))
    
    anlik_fiyat = bilgi.get('currentPrice')
    if anlik_fiyat is None:
        anlik_fiyat = gecmis_hizli['Close'].iloc[-1] if not gecmis_hizli.empty else 0.0
        
    onceki_kapanis = bilgi.get('previousClose')
    if onceki_kapanis is None or onceki_kapanis == 0:
        onceki_kapanis = anlik_fiyat 
    
    degisim_yuzde = ((anlik_fiyat - onceki_kapanis) / onceki_kapanis) * 100 if onceki_kapanis > 0 else 0.0
        
    if degisim_yuzde > 0:
        delta_metni = f"{degisim_yuzde:.2f}%"
        renk_ayari = "normal"
    elif degisim_yuzde < 0:
        delta_metni = f"{degisim_yuzde:.2f}%" 
        renk_ayari = "normal"
    else:
        delta_metni = "0.00%"
        renk_ayari = "off" 

    st.metric(
        label="Anlık Fiyat", 
        value=f"{anlik_fiyat:.2f} TL", 
        delta=delta_metni,
        delta_color=renk_ayari
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    tavan = onceki_kapanis * 1.10
    taban = onceki_kapanis * 0.90
    
    col1.metric("Taban", f"{taban:.2f}")
    col2.metric("Tavan", f"{tavan:.2f}")
    col3.metric("Yüksek", f"{bilgi.get('dayHigh', 0):.2f}")
    col4.metric("Düşük", f"{bilgi.get('dayLow', 0):.2f}")
    col5.metric("Önc.Kap.", f"{onceki_kapanis:.2f}")

    st.markdown("---")
    st.markdown("### 📈 Grafik ve Teknik Göstergeler")

    if not gecmis_veri.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=gecmis_veri.index, 
            y=gecmis_veri['Close'], 
            mode='lines', 
            name='Kapanış Fiyatı',
            line=dict(color='#29b6f6', width=2)
        ))
        fig.update_layout(
            height=500,
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_title="Tarih",
            yaxis_title="Fiyat",
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        alt_col1, alt_col2 = st.columns(2)
        with alt_col1:
            st.write(f"**Sektör:** {bilgi.get('sector', 'Bilinmiyor')}")
            st.write(f"**F/K:** {bilgi.get('trailingPE', 'N/A')}")
            pddd = bilgi.get('priceToBook')
            st.write(f"**PD/DD:** {f'{pddd:.2f}' if isinstance(pddd, (int, float)) else 'N/A'}")
            
        with alt_col2:
            st.write(f"**Endüstri:** {bilgi.get('industry', 'Bilinmiyor')}")
            st.write(f"**FD/FAVÖK:** {bilgi.get('enterpriseToEbitda', 'N/A')}") 
            pd_degeri = bilgi.get('marketCap', 'N/A')
            st.write(f"**Piyasa Değeri:** {f'{pd_degeri:,}' if isinstance(pd_degeri, (int, float)) else 'N/A'}")
            hacim_degeri = bilgi.get('volume', 'N/A')
            st.write(f"**Hacim Lot:** {f'{hacim_degeri:,}' if isinstance(hacim_degeri, (int, float)) else 'N/A'}")