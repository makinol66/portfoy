import streamlit as st
from tefasfon import get_funds
import pandas as pd
from datetime import datetime, timedelta

# Sayfa genel ayarları
st.set_page_config(page_title="TEFAS Fon Analiz", page_icon="📈", layout="wide")

st.title("📈 TEFAS Fon Analiz Uygulaması")
st.write("Bu uygulama üzerinden fon kodunu girerek geçmiş verileri analiz edebilirsiniz.")

# Sol taraftaki menüyü (Sidebar) oluşturuyoruz
st.sidebar.header("Arama Kriterleri")

fon_tipleri = {
    "Yatırım Fonları (AFT, YAY, IDH vb.)": "SEC",
    "Emeklilik Fonları": "PEN",
    "Borsa Yatırım Fonları": "ETF",
    "Gayrimenkul Yatırım Fonları": "RE",
    "Girişim Sermayesi Fonları": "VC"
}

secilen_tip_metni = st.sidebar.selectbox("Fon Tipi:", list(fon_tipleri.keys()))
fon_tipi_kodu = fon_tipleri[secilen_tip_metni]

fon_kodu = st.sidebar.text_input("Fon Kodu (Örn: AFT, IDH, YAY):", "AFT").upper()

# Tarih ayarları (Bitiş tarihini varsayılan olarak dün yapıyoruz ki bugünün eksik verisi hata vermesin)
bugun = datetime.today()
dun = bugun - timedelta(days=1)
gecen_ay = dun - timedelta(days=30)

baslangic = st.sidebar.date_input("Başlangıç Tarihi", gecen_ay)
bitis = st.sidebar.date_input("Bitiş Tarihi", dun)

# "Verileri Getir" butonuna basıldığında çalışacak kodlar
if st.sidebar.button("Verileri Getir"):
    with st.spinner(f"{fon_kodu} verileri TEFAS'tan çekiliyor..."):
        try:
            start_str = baslangic.strftime("%d.%m.%Y")
            end_str = bitis.strftime("%d.%m.%Y")

            # Veriyi çekiyoruz
            df = get_funds(
                fund_type=fon_tipi_kodu, 
                start_date=start_str, 
                end_date=end_str,
                fund_codes=[fon_kodu]
            )

            if df is not None and not df.empty:
                st.success("Veriler başarıyla getirildi!")
                
                # İŞTE ÇÖZÜLEN KISIM BURASI: Format dayatması yapmadan pandas'ın otomatik anlamasını sağlıyoruz
                df['tarih'] = pd.to_datetime(df['tarih'], format='mixed')
                df = df.sort_values("tarih")

                # Metrik gösterimi
                son_fiyat = df.iloc[-1]['fiyat']
                st.metric(label=f"{fon_kodu} - Son Fiyat (TL)", value=f"{son_fiyat:.6f}")

                # Grafik
                st.subheader("Fiyat Değişim Grafiği")
                grafik_verisi = df.set_index('tarih')['fiyat']
                st.line_chart(grafik_verisi)

                # Tabloyu Türkçe başlıklarla gösterelim
                st.subheader("Detaylı Veri Tablosu")
                df_gosterim = df.copy()
                df_gosterim['tarih'] = df_gosterim['tarih'].dt.strftime("%d.%m.%Y") # Ekranda bizim alıştığımız formatta göstersin
                st.dataframe(df_gosterim, use_container_width=True)

            else:
                st.warning(f"{fon_kodu} kodu için bu tarih aralığında veri bulunamadı.")
                
        except Exception as e:
            st.error(f"Veri işlenirken bir hata oluştu: {e}")